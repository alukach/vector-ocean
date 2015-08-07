import math
import os
import shutil
import subprocess
import sys
import tempfile

import rasterio


devnull = open(os.devnull, 'w')


def task(file_path, output_dir, col, row, src_width, src_height, clipfile_path=None, zoom=8, vert_exag=20, thresholds=(30, 50, 70, 80), verbosity=1):
    """
    - Subset file
    - Hillshade data
    - Monochrome data
    - Polygonize
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        overlap = float(2)
        num_rows = math.pow(2, zoom)
        width = overlap * src_width / num_rows
        height = overlap * src_height / num_rows
        x = (col * width / overlap) - (1/overlap * width)
        y = (row * height / overlap) - (1/overlap * height)

        # Subset data
        subset_path = "{tmpdir}/{x}_{y}_subset.tif".format(x='%05d' % x, y='%05d' % y, tmpdir=tmpdir)
        cmd = "gdal_translate -srcwin {x} {y} {width} {height} -of GTIFF {input} {output}"
        cmd = cmd.format(x=x, y=y, width=width, height=height, input=file_path, output=subset_path)
        if verbosity > 1:
            print(cmd)
        subprocess.check_call(cmd, shell=True, stdout=devnull, stderr=devnull)

        # Crop data
        if clipfile_path:
            clipfile_subset_path = "{tmpdir}/clipfile_subset.shp".format(tmpdir=tmpdir)
            cmd = "ogr2ogr -f \"ESRI Shapefile\" {clipfile_subset_path} {clipfile_path} -clipsrc {x_min} {y_min} {x_max} {y_max}"
            cmd = cmd.format(
                clipfile_subset_path=clipfile_subset_path, clipfile_path=clipfile_path,
                x_min=x, y_min=y, x_max=(x + width), y_max=(y + height)
            )
            if verbosity > 1:
                print(cmd)
            subprocess.check_call(cmd, shell=True, stdout=devnull, stderr=devnull)
            clipped_subset_path = "{tmpdir}/subset_clipped.tif".format(tmpdir=tmpdir)
            cmd = "gdalwarp -cutline {clipfile_subset_path} {input} {output}"
            cmd = cmd.format(
                clipfile_subset_path=clipfile_subset_path,
                input=subset_path, output=clipped_subset_path
            )
            if verbosity > 1:
                print(cmd)
            subprocess.check_call(cmd, shell=True, stdout=devnull, stderr=devnull)
            subset_path = clipped_subset_path

        # Hillshade data
        hillshade_path = "{}_hillshade_{}.tif".format(subset_path, vert_exag)
        cmd = "gdaldem hillshade -co compress=lzw -compute_edges -z {vert} {input} {output}"
        cmd = cmd.format(vert=vert_exag, input=subset_path, output=hillshade_path)
        if verbosity > 1:
            print(cmd)
        subprocess.check_call(cmd, shell=True, stdout=devnull, stderr=devnull)

        # Thresholds
        threshold_base = "{}_threshold".format(hillshade_path)
        threshold_path_tmplt = threshold_base + "_threshold_{threshold}.tif"
        for threshold in thresholds:
            threshold_path = threshold_path_tmplt.format(threshold=threshold)
            cmd = "convert {input} -threshold {threshold}% {output}"
            cmd = cmd.format(input=hillshade_path, output=threshold_path, threshold=threshold)
            if verbosity > 1:
                print(cmd)
            subprocess.check_call(cmd, shell=True, stdout=devnull, stderr=devnull)
        threshold_paths = " ".join([threshold_path_tmplt.format(threshold=threshold) for threshold in thresholds])

        # Combine thresholds
        combined_path = "{}_combined.gif".format(hillshade_path)
        cmd = "convert {threshold_paths} -evaluate-sequence mean {output}"
        cmd = cmd.format(threshold_paths=threshold_paths, output=combined_path)
        if verbosity > 1:
            print(cmd)
        subprocess.check_call(cmd, shell=True, stdout=devnull, stderr=devnull)

        # Convert
        combined_tif_path = "{}.tif".format('.'.join(combined_path.split('.')[:-1]))
        cmd = "convert {input} {output}".format(input=combined_path, output=combined_tif_path)
        if verbosity > 1:
            print(cmd)
        subprocess.check_call(cmd, shell=True, stdout=devnull, stderr=devnull)

        # Re-apply geodata
        if verbosity > 1:
            print(cmd)
        cmd = "listgeo -tfw {}".format(subset_path)
        subprocess.check_call(cmd, shell=True, stdout=devnull, stderr=devnull)
        cmd = "mv {input}.tfw {output}.tfw"
        cmd = cmd.format(
            input='.'.join(subset_path.split('.')[:-1]),
            output='.'.join(combined_tif_path.split('.')[:-1])
        )
        if verbosity > 1:
            print(cmd)
        subprocess.check_call(cmd, shell=True, stdout=devnull, stderr=devnull)

        # Polygonize
        geojson_path = "{}.geojson".format(combined_tif_path)
        cmd = "gdal_polygonize.py {input} -f GeoJSON {output}"
        cmd = cmd.format(input=combined_tif_path, output=geojson_path)
        if verbosity > 1:
            print(cmd)
        subprocess.check_call(cmd, shell=True, stdout=devnull, stderr=devnull)

        # Mv to output
        out_dir = "{base}/{z}/{x}".format(base=output_dir, z=zoom, x=col)
        os.makedirs(out_dir, exist_ok=True)
        cmd = "mv {input} {out_dir}/{y}.geojson".format(input=geojson_path, out_dir=out_dir, y=row)
        if verbosity > 1:
            print(cmd)
        subprocess.check_call(cmd, shell=True, stdout=devnull, stderr=devnull)

        print('.', end='\n' if verbosity > 1 else '.')
        sys.stdout.flush()


def scheduler(file_path, output_dir, clipfile_path=None, tile_size=512):
    with rasterio.drivers():
        with rasterio.open(file_path) as src:
            width = src.width
            height = src.height

    zoom = 8
    for z in range(zoom, zoom+1):
        num_rows = int(math.pow(2, z))
        for col in range(0, num_rows):
            for row in range(0, num_rows):
                kwargs = dict(
                    file_path=file_path, output_dir=output_dir,
                    clipfile_path=clipfile_path,
                    col=col, row=row, zoom=z,
                    src_width=width, src_height=height,
                    vert_exag=20, thresholds=(30, 50, 70, 80)
                )
                task(**kwargs)


if __name__ == '__main__':

    import argparse

    parser = argparse.ArgumentParser(
        description="Concurrent raster processing demo")
    parser.add_argument(
        'input',
        metavar='INPUT',
        help="Input file name")
    parser.add_argument(
        '--clipfile',
        metavar='CLIPFILE',
        help="Clipping Shapefile")
    parser.add_argument(
        '--outdir',
        metavar='OUTPUT_DIR',
        default='./out',
        help="Output Directory")

    args = parser.parse_args()
    scheduler(args.input, args.outdir, args.clipfile)
