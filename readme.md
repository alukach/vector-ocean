# Generating an Ocean Vector Terrain tile source

Based off of Mapbox' [Global Vector Terrain slide deck](https://speakerdeck.com/mapbox/global-vector-terrain).

One thing that was not initially clear was how to handle features that span multiple tiles. Should we clip features that span multiple tiles? If so, does the [vector tile spec](https://github.com/mapbox/vector-tile-spec) differentiate between features that are clipped vs features that naturally end at the boundary of the tile? Is only the boundary of the polygon included, or are extra lines at the tile boundary added to "close" the polygon within the tile?  There are multiple issues regarding this topic ([4](https://github.com/mapbox/vector-tile-spec/issues/4), [8](https://github.com/mapbox/vector-tile-spec/issues/8), [26](https://github.com/mapbox/vector-tile-spec/issues/26)), but the best summary for how Mapbox handles this comes from @pramsey's [comment](https://github.com/mapbox/vector-tile-spec/issues/26#issuecomment-63902337):

> It’s a “trick” a “hack” kind of. The tiles are clipped to be slightly *larger* [than] a perfect tile would be, and then when it is render time, the render canvas is set to the *exact* tile size. The result is that edge artifacts end up outside the render frame and the rendered tiles all magically line up. It makes me feel a little dirty (the correct clipping buffer is a bit of a magic number that depends on the rendering rules that are going to be applied later) but it does serve to reinforce that vector tiles in this spec are not meant to be used as a replacement for a real vector feature service (be it a WFS, ac ArcGIS service, or some other web service), but as an improved transport for rendering, first and foremost.

Being that dialing-in the correct clipping buffer will depend on the rendering rules, I think it would be wise to split the generation of vector tiles into two main sections:

1. Vectorize input data and store in a database
1. Render vector tiles and store in cloud

## I. Vectorize & Store

### Requirements

* ImageMagick
* GDAL
* libgeotiff
* Postgresql
* PostGIS

### General Steps

1. Get the data
1. Downsample data
1. Subset Data (for dev)
1. Hillshade data
1. Convert to Monochrome Levels
1. Polygonize / Load into DB

### 1. Sourcing Data

Download GEBCO data...

_TODO: Fill this in_



### 2. Downsample



### 3. Subset data

http://gis.stackexchange.com/questions/34795/how-to-use-gdal-utilities-to-subset-from-a-raster

```bash
gdal_translate -projwin -90 32 -78 24 data/GEBCO_2014_1D.nc output/subset.tif -of GTIFF
```


### 4. Hillshade

Convenience function to help experiment with finding the right hillshade level using GDAL.

``` bash
# example usage: hillshade subset.tif .1
hillshade () {
    echo "gdaldem hillshade -co compress=lzw -compute_edges -z $2 $1 $1_hillshade_$2.tif";
    gdaldem hillshade -co compress=lzw -compute_edges -z $2 $1 $1_hillshade_$2.tif;
}
```

Using `-co compress=lzw` and `-compute` to [compress the TIFF and avoid black pixel border around the edge of the image](https://www.mapbox.com/tilemill/docs/guides/terrain-data/#creating-hillshades), respectively.

![Hillshade Tests](imgs/hillshade_montage.jpg)

At first blush, it appears that a vertical exaggeration at `0.001` best illustrates the elevation model (looking at the inland regions) but notice that much of the coastal region (such as the [Viosca Knoll area](http://soundwaves.usgs.gov/2011/03/DeepF1sm2LG.jpg)) lies within shadows. It is important to ensure that variation amongst features is not obscured. Bringing out subtle variances can be done with well-chosen thresholds during the conversion to monochrome levels.

_Idea: Adjust altitude as zoom level surpasses natural resolution to minimize objects entirely within shade_

### 5. Convert to Monochrome Levels

You're going to want to produce ~4 monochromatic layers representing varying depths. To do so, we'll use ImageMagick's [threshold](http://www.imagemagick.org/script/command-line-options.php#threshold) utility.

#### 5a. Threshold

``` bash
# example usage: monochrome subset.tif 50%
monochrome () {
    echo "convert $1 -threshold $2% $1_monochrome_$2.tif";
    convert $1 -threshold $2% $1_monochrome_$2.tif;
}
```

This command will likely some `Unknown field with tag ...` warnings during runtime. This is due to ImageMagick is not geo-aware. As such, geo fields are not copied to the new images produced. We'll reapply this data later.

![Monochrome Tests](imgs/monochrome_montage.jpg)

I started with an equally distributed range of thresholds (`20 40 60 80`), and fine-tuned from there based on aesthetics. A lot can be gained from spending some time experimenting with varying thresholds. Initially, almost all inland mountains we limited to being only illustrated by their peaks. Eventually, I found that a threshold of `75` illustrated plenty of the inland features.


#### 5b. Merge

To get a visualization of the output, merge the images into a single image:

``` bash
convert subset.tif_hillshade_.0001.tif_monochrome_* -evaluate-sequence mean subset.tif_hillshade_monochrome_combined.gif
```

![merged monochrome](imgs/subset.tif_hillshade_monochrome_combined.gif)

Oddly, this command failed when attempting to create a TIFF. Instead, I created a GIF output (I initially used JPEG, but opted for GIF due to smaller filesize and no-artifacts).

![Artifacts](imgs/artifact_montage.png)


This can then be converted to TIFF via:

``` bash
convert subset.tif_hillshade_monochrome_combined.gif subset.tif_hillshade_monochrome_combined.tif
```

#### 5c. Re-apply geodata

Since ImageMagick stripped the imagery of its geospatial attributes, we'll need to reapply them somehow. Luckily, GDAL knows to look for a matching .tfw if it sees a TIFF that isn’t internally georeferenced. Since we haven't actually changed any spatial information regarding the imagery, we can take the spatial information from the original `subset.tiff` and name it to match the new `subset.tif_hillshade_monochrome_combined.tfw`:

``` bash
listgeo -tfw subset.tif && mv subset.tfw subset.tif_hillshade_monochrome_combined.tfw
```


### 6. Polygonize / Load into DB

Simplify to remove pixelization

``` bash
gdal_polygonize.py subset.tif_hillshade_monochrome_combined.tif -f GeoJSON subset.tif_hillshade_monochrome_combined.tif_polygons.geojson
```

![Polygonized Data viewed in QGIS](imgs/polygonized.png)

_Note: Should we then dissolve/aggregate polygons between subsets that share borders? [[1]](http://gis.stackexchange.com/questions/85028/dissolve-aggregate-polygons-with-ogr2ogr-or-gpc)_

## II. Generate Tiles




## Notes

### Resources

[Mapbox: Processing Landsat 8 Using Open-Source Tools](https://www.mapbox.com/blog/processing-landsat-8/)

_Note: Gridded output of images were created with:_

``` bash
montage -label '%f' subset.tif_hillshade_* -tile 2x -geometry '480x320' montage.jpg
```

_Advanced labeling:_

``` bash
unset arguments
for f in subset.tif_hillshade_.0001.tif_monochrome_*; do
    var=${f#*_*_*_*_} var=${var%%.*};
    arguments+=(-label "Threshold: $var" "$f");
done
montage "${arguments[@]}" -tile 2x -geometry 480 ../../imgs/monochrome_montage.jpg
```
