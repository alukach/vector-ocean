var async = require('async');
var fs = require('fs');
var util = require('util');
var os = require('os');
var path = require('path');
var spawn = require('child_process').spawnSync;

var tilelive = require('tilelive');
var argv = require('minimist')(process.argv.slice(2));
var mkdirp = require('mkdirp');

require('mbtiles').registerProtocols(tilelive);
require('tilelive-tmsource')(tilelive);


var minzoom = 1;
var maxzoom = 2;
var bucket = 'ocean2';

tilelive.load('tmsource://../tile-server/mapbox_studio.tm2source', function(err, source) {
    // Queue Handler
    var q = async.queue(function (task, callback) {
        var url = util.format('%s/%s/%s', task.z, task.x, task.y);
        console.log('Procesessing ' + url);
        source.getTile(task.z, task.x, task.y, function(err, tile, headers) {
            if (err) {
                console.log(url, ' failed!');
            } else {
                // Save to tmpfile
                var fname = url + '.pbf';
                var fdir = os.tmpdir();
                var fpath = path.join(fdir, fname);
                console.log(fpath);
                mkdirp(path.dirname(fpath), function (err) {
                    if (err) throw (err);

                    fs.writeFile(fpath, tile, function (err) {
                        if (err) throw (err);

                        // Upload to Swift
                        var headers = " -H 'Content-Type: application/x-protobuf' -H 'X-Container-Meta-Access-Control-Allow-Origin: *'";
                        results = spawn('swift', ['upload', bucket, fname], {cwd: path.dirname(fpath)});
                        if (results.error) throw (results.error);
                        // console.log("Wrote ", results.output);
                        console.log("Stdout: ", results.stdout.toString());
                        console.log("Stderr: ", results.stderr.toString());
                        console.log("Status: ", results.status);
                        console.log("Error: ", results.error);
                    });
                });
                callback();
            }
        });
    }, 2);

    // Finishing Message
    q.drain = function() {
        console.log('all items have been processed');
        return process.exit();
    };

    // Queue up jobs
    function callback (err) {
        if (err) {
            console.error(err);
        } else {
            console.log(util.format('Processed %s', url));
        }
    }
    for (var z in range(minzoom, maxzoom + 1)) {
        for (var x in range(0, Math.pow(2, z))) {
            for (var y in range(0, Math.pow(2, z))) {
                var url = util.format('%s/%s/%s', z, x, y);
                var zxy = [z, x, y];
                console.log("Adding the following to the queue: ", zxy);
                q.push({z:z, x:x, y:y}, callback);
            }
        }
    }
});


/**
 * Generates an array containing arithmetic progressions
 * @param  {number} start Beginning integer
 * @param  {number} stop  Ending integer, exclusive
 * @return {array}        Array of numbers between start and stop, exclusive
 */
function range(start, stop) {
    return Array.apply(Array, Array(stop - start)).map(
        function (_, i) {
            return i + start;
        }
    );
}
