var express = require('express');
var http = require('http');
var tilelive = require('tilelive');
var fs = require('fs');
var mkdirp = require('mkdirp');
var path = require('path');
var argv = require('minimist')(process.argv.slice(2));

require('mbtiles').registerProtocols(tilelive);
require('tilelive-tmsource')(tilelive);

var app = express();
tilelive.load('tmsource://./mapbox_studio.tm2source', function(err, source) {

    if (err) {
        throw err;
    }
    app.set('port', 7777);

    app.use(function(req, res, next) {
        res.header("Access-Control-Allow-Origin", "*");
        res.header("Access-Control-Allow-Headers", "Origin, X-Requested-With, Content-Type, Accept");
        next();
    });

    app.get(/^\/tiles\/(\d+)\/(\d+)\/(\d+).pbf$/, function(req, res){

        var z = req.params[0];
        var x = req.params[1];
        var y = req.params[2];

        var cache_path = path.join(argv.cachedir, "{z}/{x}/{y}.pbf");
        cache_path = cache_path.replace("{z}", z).replace("{x}", x).replace("{y}", y);

        // Look for file in cache
        fs.stat(cache_path, function(err, stat) {
            // Serve from cache
            if (stat) {
                console.log('get tile %d, %d, %d from cache', z, x, y);
                res.header('Content-Type', 'application/x-protobuf');
                res.header('Content-Encoding', 'gzip');
                fs.createReadStream(cache_path).pipe(res);
            // Not in cache, get from DB
            } else {
                console.log('get tile %d, %d, %d from db', z, x, y);
                source.getTile(z, x, y, function(err, tile, headers) {
                    if (err) {
                        res.status(404);
                        res.send(err.message);
                        console.log(err.message);
                    } else {
                        res.set(headers);
                        res.send(tile);

                        // Cache to disk
                        if (argv.cachedir) {
                            mkdirp(path.dirname(cache_path), function (err) {
                                if (err) return console.error(err);
                                fs.writeFile(cache_path, tile, function(err) {
                                    if(err) return console.log(err);
                                    console.log('wrote %d, %d, %d to cache', z, x, y);
                                });
                            });
                        }
                    }
                });
            }
        });
    });

    http.createServer(app).listen(app.get('port'), function() {
        console.log('Express server listening on port ' + app.get('port'));
    });
});
