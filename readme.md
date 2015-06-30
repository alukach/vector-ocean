# Generating a Ocean Vector Terrain tile source

Based off of Mapbox' [Global Vector Terrain slide deck](https://speakerdeck.com/mapbox/global-vector-terrain).

1. Get the data
1. Subset Data?
1. Hillshade data
1. Mask data?
1. Polygonize



## Step 1: Sourcing Data

Download GEBCO data...

_TODO: Fill this in_

## Step 2: Subset data

http://gis.stackexchange.com/questions/34795/how-to-use-gdal-utilities-to-subset-from-a-raster

```bash
gdal_translate -srcwin 5000 5000 6000 6000 ../mksurface/RN-7496_1426563692680/GEBCO_2014_1D.nc 0-0-1000-1000.tif
```



## Step : Polygonize

`gdal_polygonize.py`

## Step 4: ImageMagick
