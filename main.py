import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

import rasterio


def task(file_path, db_name, table_name,
        col, row, src_width, src_height, num_rows,
        clipfile_path, vert_exag, thresholds,
        verbosity, pause):
    """
    General steps:
    - Subset file
    - Hillshade data
    - Monochrome data
    - Polygonize
    """
    # TODO:
    # - Downsample data for lower zoom-levels
    # - Add countouring
    # - Run polygonize on each threshold image, not combined? (No holes in coverage)
    # - Vertical exageration correction on different zoom levels?

    with tempfile.TemporaryDirectory() as tmpdir:
        overlap = float(2)
        width = overlap * src_width / num_rows
        height = overlap * src_height / num_rows
        # TODO: If x or y is negative, handle getting selection from other
        # side of image and joining.
        x = (col * width / overlap) - (1/overlap * width/2)
        y = (row * height / overlap) - (1/overlap * height/2)

        # Subset data
        subset_path = "{tmpdir}/{x}_{y}_subset.tif".format(x='%05d' % x, y='%05d' % y, tmpdir=tmpdir)
        cmd = "gdal_translate -srcwin {x} {y} {width} {height} -of GTIFF {input} {output}"
        cmd = cmd.format(x=x, y=y, width=width, height=height, input=file_path, output=subset_path)
        if verbosity > 1:
            print(cmd)
        subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Clip data
        if clipfile_path:
            clipfile_subset_path = "{tmpdir}/clipfile_subset.shp".format(tmpdir=tmpdir)
            cmd = "ogr2ogr -f \"ESRI Shapefile\" {clipfile_subset_path} {clipfile_path} -clipsrc {x_min} {y_min} {x_max} {y_max}"
            cmd = cmd.format(
                clipfile_subset_path=clipfile_subset_path, clipfile_path=clipfile_path,
                x_min=x, y_min=y, x_max=(x + width), y_max=(y + height)
            )
            if verbosity > 1:
                print(cmd)
            subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            clipped_subset_path = "{tmpdir}/subset_clipped.tif".format(tmpdir=tmpdir)
            cmd = "gdalwarp -cutline {clipfile_subset_path} {input} {output}"
            cmd = cmd.format(
                clipfile_subset_path=clipfile_subset_path,
                input=subset_path, output=clipped_subset_path
            )
            if verbosity > 1:
                print(cmd)
            subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subset_path = clipped_subset_path

        # Hillshade data
        hillshade_path = "{}_hillshade_{}.tif".format(subset_path, vert_exag)
        cmd = "gdaldem hillshade -co compress=lzw -compute_edges -z {vert} {input} {output}"
        cmd = cmd.format(vert=vert_exag, input=subset_path, output=hillshade_path)
        if verbosity > 1:
            print(cmd)
        subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Thresholds
        threshold_base = "{}_threshold".format(hillshade_path)
        threshold_path_tmplt = threshold_base + "_threshold_{threshold}.tif"
        for threshold in thresholds:
            threshold_path = threshold_path_tmplt.format(threshold=threshold)
            cmd = "convert {input} -threshold {threshold}% {output}"
            cmd = cmd.format(input=hillshade_path, output=threshold_path, threshold=threshold)
            if verbosity > 1:
                print(cmd)
            subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        threshold_paths = " ".join([threshold_path_tmplt.format(threshold=threshold) for threshold in thresholds])

        # Combine thresholds
        combined_path = "{}_combined.gif".format(hillshade_path)
        cmd = "convert {threshold_paths} -evaluate-sequence mean {output}"
        cmd = cmd.format(threshold_paths=threshold_paths, output=combined_path)
        if verbosity > 1:
            print(cmd)
        subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Convert
        combined_tif_path = "{}.tif".format('.'.join(combined_path.split('.')[:-1]))
        cmd = "convert {input} {output}".format(input=combined_path, output=combined_tif_path)
        if verbosity > 1:
            print(cmd)
        subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Re-apply geodata
        if verbosity > 1:
            print(cmd)
        cmd = "listgeo -tfw {}".format(subset_path)
        subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cmd = "mv {input}.tfw {output}.tfw"
        cmd = cmd.format(
            input='.'.join(subset_path.split('.')[:-1]),
            output='.'.join(combined_tif_path.split('.')[:-1])
        )
        if verbosity > 1:
            print(cmd)
        subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Polygonize
        geojson_path = "{}.geojson".format(combined_tif_path)
        cmd = "gdal_polygonize.py {input} -f PostgreSQL PG:dbname={db_name} {table_name} value"
        cmd = cmd.format(input=combined_tif_path, db_name=db_name, table_name=table_name)
        if verbosity > 1:
            print(cmd)
        subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # TODO: Smooth polygons
        # TODO: Remove non-shadow/highlight polygons (middle threshold value?)

        if pause:
            input(tmpdir)

        return "{} - {}".format(col, row)


def scheduler(clear_tables=False, celery=False, **kwargs):
    with rasterio.drivers():
        with rasterio.open(kwargs['file_path']) as src:
            width = src.width
            height = src.height

    # Prepare threading tooling
    if not celery:
        from queue import Queue
        q = Queue()

    zoom = 8
    # Queue work
    for z in range(zoom, zoom+1):
        num_rows = int(math.pow(2, z))
        table_name = z

        if clear_tables:
            cmd = 'psql {db_name} -c "DROP TABLE IF EXISTS \\"{table_name}\\""'
            cmd = cmd.format(db_name=kwargs['db_name'], table_name=table_name)
            subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for col in range(0, num_rows):
            for row in range(0, num_rows):
                task_kwargs = kwargs.copy()
                task_kwargs.update({
                    'table_name': table_name,
                    'num_rows': num_rows,
                    'src_width': width,
                    'src_height': height,
                    'col': col,
                    'row': row,
                    'vert_exag': 20,
                    'thresholds': (30, 50, 70, 80),
                })

                # Insert into Thread queue
                if not celery:
                    q.put(task_kwargs)
                # Insert into Celery queue
                else:
                    task(**task_kwargs)

                    if not kwargs['verbosity']:
                        tile_num = (row + (col*num_rows) + 1)
                        total = int(math.pow(num_rows, 2))
                        percentage = '%.4f' % (tile_num*100.0 / total)
                        status = 'processed' if not celery else 'scheduled'
                        msg = "\r{}% {} ({}/{})".format(percentage, status, tile_num, total)
                        print(msg, end="")

        # Process queue
        if not celery:
            from concurrent.futures import ThreadPoolExecutor as Pool
            import multiprocessing
            import functools

            def counter(future):
                counter.processed += 1
                percentage = '%.4f' % (counter.processed*100.0 / counter.to_process)
                msg = "\r{}% processed ({}/{})".format(percentage, counter.processed, counter.to_process)
                print(msg, end="")
            counter.processed = 0
            counter.to_process = int(math.pow(num_rows, 2))

            with Pool(max_workers=multiprocessing.cpu_count() * 2) as executor:
                while not q.empty():
                    kwargs = q.get()
                    future = executor.submit(task, **kwargs).add_done_callback(counter)

        print("\nComplete")


if __name__ == '__main__':

    import argparse

    parser = argparse.ArgumentParser(
        description="Concurrent raster processing demo")
    parser.add_argument(
        'file_path',
        metavar='INPUT',
        help="Input file name")
    parser.add_argument(
        '--clipfile',
        dest='clipfile_path',
        metavar='CLIPFILE_PATH',
        help="Clipping Shapefile")
    parser.add_argument(
        '--verbose', '-v',
        dest='verbosity',
        default=0,
        action='count')
    parser.add_argument(
        '--pause', '-p',
        action='store_true',
        default=False,
        help=('Wait for input after each tile is generated, before '
            'temporary directory is removed. For development/testing '
            'purposes.'))
    parser.add_argument(
        '--db_name', '-db',
        dest='db_name',
        metavar='DB_NAME',
        default='ocean-tiles',
        help="Output Database")
    parser.add_argument(
        '--clear-tables',
        action='store_true',
        default=False,
        help="Clear destination tables before creating tiles")
    parser.add_argument(
        '--celery',
        action='store_true',
        default=False,
        help="Process asynchronously with Celery")
    args = parser.parse_args()
    try:
        scheduler(**args.__dict__)
    except KeyboardInterrupt:
        print("Received exit signal, shutting down...")
        sys.exit()
