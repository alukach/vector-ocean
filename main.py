import rasterio

def scheduler(filename, tile_size=512):
    with rasterio.drivers():
        with rasterio.open(filename) as src:
            width = src.width
            height = src.height

    for row in range(int(height / tile_size) + 1):
        for col in range(int(width / tile_size) + 1):
            data = dict(
                col=col,
                row=row,
                x=(col * width),
                y=(row * height),
            )
            print("col:{col} x row:{row}, ({x}, {y})".format(**data))
        

if __name__ == '__main__':

    import argparse

    parser = argparse.ArgumentParser(
        description="Concurrent raster processing demo")
    parser.add_argument(
        'input',
        metavar='INPUT',
        help="Input file name")
    # parser.add_argument(
    #     'output',
    #     metavar='OUTPUT',
    #     help="Output file name")
    # parser.add_argument(
    #     '--async',
    #     action='store_true',
    #     help="Run with a pool of worker threads")
    args = parser.parse_args()

    scheduler(args.input)
