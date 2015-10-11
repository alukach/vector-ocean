var async = require('async');
var fs = require('fs');
var util = require('util');
var os = require('os');
var path = require('path');
var exec = require('child_process').exec;

var tilelive = require('tilelive');
var argv = require('minimist')(process.argv.slice(2));
var mkdirp = require('mkdirp');

require('mbtiles').registerProtocols(tilelive);
require('tilelive-tmsource')(tilelive);

var program = require('commander');

program
	.version(0.1)
    .option('-z, --minimum-zoom <zoom>', 'Minimum zoom level to process (defaults to 0).', parseInt)
    .option('-Z, --maximum-zoom <zoom>', 'Maximum zoom level to process (defaults to 6).', parseInt)
    .option('-b, --bucket <name>', 'Bucket in which to upload results (defaults to \'bathy\').')
	.option('-c, --concurrency <count>', 'Number of concurrent tile operations (defaults to 2).', parseInt)
	.parse(process.argv);

var minzoom = program.minimumZoom || 0;
var maxzoom = program.maximumZoom || 6;
var bucket = program.bucket || 'bathy';
var concurrency = program.concurrency || 2;

tilelive.load('tmsource://../tile-server/mapbox_studio.tm2source', function(err, source) {
    // Queue Handler
    var q = async.queue(tileUploaderTask, 2);

    // Finishing Message
    q.drain = function() {
        var cmd = util.format('swift post %s -H \'X-Container-Meta-Access-Control-Allow-Origin: *\'', bucket);
        runCmd(cmd);
        console.log('all items have been processed');
        return process.exit();
    };

    // Queue up jobs
    function callback (url) {
        console.log(util.format('Processed %s', url));
    }
    var levels = range(minzoom, maxzoom + 1);
    for (var i=0; i < levels.length; i++) {
        var z = levels[i];
        for (var x in range(0, Math.pow(2, z))) {
            for (var y in range(0, Math.pow(2, z))) {
                var url = util.format('%s/%s/%s', z, x, y);
                var zxy = [z, x, y];
                console.log("Adding the following to the queue:", url);
                q.push({z:z, x:x, y:y}, callback);
            }
        }
    }

    // Task
    function tileUploaderTask(task, callback) {
        var url = util.format('%s/%s/%s', task.z, task.x, task.y);
        console.log('Procesessing ' + url);

        source.getTile(task.z, task.x, task.y, handleTile);

        function handleTile(err, tile, headers) {
            if (err) {
                console.log(url, ' failed!');
            } else {
                // Save to tmpfile
                var fname = url + '.pbf';
                // var fdir = os.tmpdir();
                var fdir = '/tmp';
                var fpath = path.join(fdir, fname);

                mkdirp(path.dirname(fpath), writeFile);
                function writeFile(err) {
                    if (err) throw (err);
                    fs.writeFile(fpath, tile, uploadAndRmFile);
                }
                function uploadAndRmFile(err) {
                    if (err) throw (err);
                    cmd = 'swift upload ' + bucket + ' -H \'Content-Encoding: gzip\' -H \'Content-Type: application/x-protobuf\' -H \'X-Container-Meta-Access-Control-Allow-Origin: *\' ' + fname;
                    runCmd(cmd, {cwd: fdir});
                    fs.unlink(fpath);
                }

                callback(url);
            }
        }
    }
});


// Helpers

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

function runCmd(cmd, opts) {
    exec(cmd, opts, function(error, stdout, stderr) {
        // console.log('stdout: ', stdout);
        // console.log('stderr: ', stderr);
        // if (error !== null) {
            // console.log('exec error: ', error);
        // }
    });
}
