import asyncio

import rasterio
from osgeo import gdal
from numpy import gradient
from numpy import pi
from numpy import arctan
from numpy import arctan2
from numpy import sin
from numpy import cos
from numpy import sqrt
from numpy import zeros
from numpy import uint8, int16


def hillshade(array, azimuth, angle_altitude):

    x, y = gradient(array)
    slope = pi/2. - arctan(sqrt(x*x + y*y))
    aspect = arctan2(-x, y)
    azimuthrad = azimuth*pi / 180.
    altituderad = angle_altitude*pi / 180.


    shaded = sin(altituderad) * sin(slope)\
     + cos(altituderad) * cos(slope)\
     * cos(azimuthrad - aspect)
    return (255*(shaded + 1)/2).astype(int16)


def main(infile, outfile):
    with rasterio.drivers():
        with rasterio.open(infile) as src:

            meta = src.meta
            del meta['transform']
            meta.update(driver='GTiff')

            with rasterio.open(outfile, 'w', **meta) as dst:
                arr = src.read(1)
                arr = hillshade(arr, 315, 0.01)
                dst.write_band(1, arr)


def main_threaded(infile, outfile):
    with rasterio.drivers():
        with rasterio.open(infile) as src:

            meta = src.meta
            del meta['transform']
            meta.update(affine=src.affine)
            meta.update(blockxsize=256, blockysize=256, tiled='yes')
            meta.update(driver='GTiff')

            with rasterio.open(outfile, 'w', **meta) as dst:
                @asyncio.coroutine
                def copy_window(window):
                    # Write the result.
                    for i, arr in enumerate(src.read(window=window), 1):
                        arr = hillshade(arr, 315, 0.01)
                        dst.write_band(i, arr, window=window)

                # Queue up the loop's tasks.
                tasks = [asyncio.Task(copy_window(window))
                         for ij, window in dst.block_windows(1)]

                # Wait for all the tasks to finish, and close.
                loop = asyncio.get_event_loop()
                loop.run_until_complete(asyncio.wait(tasks))
                loop.close()


if __name__ == '__main__':

    import argparse

    parser = argparse.ArgumentParser(
        description="Concurrent raster processing demo")
    parser.add_argument(
        'input',
        metavar='INPUT',
        help="Input file name")
    parser.add_argument(
        'output',
        metavar='OUTPUT',
        help="Output file name")
    parser.add_argument(
        '--async',
        action='store_true',
        help="Run with a pool of worker threads")
    args = parser.parse_args()

    if args.async:
        main_threaded(args.input, args.output)
    else:
        main(args.input, args.output)
