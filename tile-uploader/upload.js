var async = require('async');
var fs = require('fs');
var util = require('util');
var os = require('os');
var path = require('path');
var exec = require('child_process').exec;

var tilelive = require('tilelive');
var argv = require('minimist')(process.argv.slice(2));
var mkdirp = require('mkdirp');
var console = require('tracer').colorConsole();

require('mbtiles').registerProtocols(tilelive);
require('tilelive-tmsource')(tilelive);

var program = require('commander');

program
	.version(0.1)
    .option('-z, --minimum-zoom <zoom>', 'Minimum zoom level to process (defaults to 0).', parseInt)
    .option('-Z, --maximum-zoom <zoom>', 'Maximum zoom level to process (defaults to 6).', parseInt)
    .option('-b, --bucket <name>', 'Bucket in which to upload results (defaults to \'bathy\').')
    .option('-c, --concurrency <count>', 'Number of concurrent tile operations (defaults to 2).', parseInt)
    .option('--starting-tile <z/x/y>', 'Starting position of upload process (in the event that you want to start processing from a specific tile)')
	.option('--limit <count>', 'Limit to total number of tiles to be processed (defaults to 0)')
	.parse(process.argv);

var minzoom = program.minimumZoom || 0;
var maxzoom = program.maximumZoom || 6;
var bucket = program.bucket || 'bathy';
var concurrency = program.concurrency || 2;
var offset = program.startingTile || null;
if (offset) {
    var xyz = offset.split('/');
    if (xyz.length != 3) throw "Improperly formatted 'starting-tile' value. Must be inf the following format: z/x/y";
    var startZ = Number(xyz[0]);
    var startX = Number(xyz[1]);
    var startY = Number(xyz[2]);

}
var limit = program.limit || null;

tilelive.load('tmsource://../tile-server/mapbox_studio.tm2source', function(err, source) {
    // Queue Handler
    var q = async.queue(tileUploaderTask, 2);

    // Finishing Message
    q.drain = function() {
        var cmd = util.format('swift post %s -H \'X-Container-Meta-Access-Control-Allow-Origin: *\'', bucket);
        exec(cmd);
        console.info('all items have been processed');
        return process.exit();
    };

    // Queue up jobs
    function callback (url) {
        console.info(util.format('Processed %s', url));
    }
    var zlevels = range(startZ || minzoom, maxzoom + 1);
    var count = 0;

    zLoop:
    for (var i=0; i < zlevels.length; i++) {
        var z = zlevels[i];
        var xlevels = range(startX || 0, Math.pow(2, z));

        xLoop:
        for (var j=0; j < xlevels.length; j++) {
            var x = xlevels[j];
            var ylevels = range(startY || 0, Math.pow(2, z));

            yLoop:
            for (var k=0; k < ylevels.length; k++) {
                var y = ylevels[k];
                var url = util.format('%s/%s/%s', z, x, y);
                console.info("Adding the following to the queue:", url);
                q.push({z:z, x:x, y:y}, callback);

                if (limit && (count += 1) >= limit) {
                    console.warn("Hit tile limit of " + limit + ". Not scheduling any more tiles");
                    break zLoop;
                }
            }
        }
    }

    // Task
    function tileUploaderTask(task, callback) {
        var url = util.format('%s/%s/%s', task.z, task.x, task.y);
        console.info('Procesessing ' + url);

        source.getTile(task.z, task.x, task.y, handleTile);

        function handleTile(err, tile, headers) {
            if (err) return console.error(url, 'failed!', err);

            // Save to tmpfile
            var fname = url + '.pbf';
            var fdir = os.tmpdir();
            var fpath = path.join(fdir, fname);

            mkdirp(path.dirname(fpath), writeFile);
            function writeFile(err) {
                if (err) throw (err);
                fs.writeFile(fpath, tile, uploadAndRmFile);
            }
            function uploadAndRmFile(err) {
                if (err) throw (err);
                cmd = 'swift upload ' + bucket + ' -H \'Content-Encoding: gzip\' -H \'Content-Type: application/x-protobuf\' -H \'X-Container-Meta-Access-Control-Allow-Origin: *\' ' + fname;
                exec(cmd, {cwd: fdir}, function(error, stdout, stderr) {
                    if (err || stderr) throw (err || stderr);
                    fs.unlink(fpath);
                });
            }
            callback(url);
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
    return Array.apply(Array, Array(Number(stop) - Number(start))).map(
        function (_, i) { return i + Number(start); }
    );
}
