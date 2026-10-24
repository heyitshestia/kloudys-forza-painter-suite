.pragma library

var frameInterval = 50;
var enterDuration = 460;
var exitDuration = 240;
var selectionDuration = 180;

// Project the wire grid into a bounded raster, without a second scene renderer.
function project(longitude, latitude, width, height) {
    var depth = Math.cos(longitude) * Math.cos(latitude);
    var perspective = 1 / (1.18 - depth * 0.32);
    return [width * 0.37 + Math.sin(longitude) * Math.cos(latitude) * width * 0.92 * perspective,
            height * 0.5 + Math.sin(latitude) * height * 0.9 * perspective];
}

function grid(context, width, height, seconds, color) {
    context.save();
    context.translate(width * 0.5, height * 0.5);
    context.rotate(Math.sin(seconds * 0.085) * 0.035 - 0.065);
    context.translate(-width * 0.5, -height * 0.5);
    context.strokeStyle = color;
    context.lineWidth = 0.7;
    var drift = (seconds * 0.07) % (Math.PI / 60);
    for (var meridian = -30; meridian <= 30; meridian++) {
        var longitude = meridian * Math.PI / 60 + drift;
        if (Math.abs(longitude) > Math.PI / 2) continue;
        context.globalAlpha = 0.12 + Math.abs(Math.sin(longitude)) * 0.32;
        context.beginPath();
        for (var sample = 0; sample <= 36; sample++) {
            var point = project(longitude, -1.48 + sample * 2.96 / 36, width, height);
            if (sample === 0) context.moveTo(point[0], point[1]);
            else context.lineTo(point[0], point[1]);
        }
        context.stroke();
    }
    for (var parallel = -25; parallel <= 25; parallel++) {
        context.globalAlpha = 0.12 + Math.abs(parallel) / 25 * 0.23;
        context.beginPath();
        for (var segment = 0; segment <= 48; segment++) {
            var p = project(-Math.PI / 2 + segment * Math.PI / 48, parallel * Math.PI / 60, width, height);
            if (segment === 0) context.moveTo(p[0], p[1]);
            else context.lineTo(p[0], p[1]);
        }
        context.stroke();
    }
    context.restore();
}

// Two paint layers give the translucent bands true front/back occlusion in 2D.
function orbitPoint(angle, radius, tilt, turn, size) {
    var x = Math.cos(angle) * radius;
    var y = Math.sin(angle) * radius * Math.cos(tilt);
    var z = Math.sin(angle) * Math.sin(tilt);
    var perspective = 1 / (1 - z * 0.18);
    return [size * 0.5 + (x * Math.cos(turn) - y * Math.sin(turn)) * perspective,
            size * 0.5 + (x * Math.sin(turn) + y * Math.cos(turn)) * perspective, z];
}

function orbits(c, size, seconds, front, color, highlight) {
    c.save();
    for (var band = 0; band < 3; band++) {
        var tilt = 0.6 + band * 0.62 + Math.sin(seconds * 0.17 + band) * 0.24;
        var turn = band * 1.05 + seconds * (band === 1 ? -0.18 : 0.13);
        var radius = size * (0.37 + band * 0.026);
        for (var step = 0; step < 72; step++) {
            var a = step * Math.PI / 36, b = (step + 1) * Math.PI / 36;
            var p = orbitPoint(a, radius, tilt, turn, size);
            var q = orbitPoint(b, radius, tilt, turn, size);
            if (((p[2] + q[2]) >= 0) !== front) continue;
            var thickness = size * (0.018 + 0.007 * Math.sin(a * 2 + seconds * 0.4 + band));
            var innerP = orbitPoint(a, radius - thickness, tilt, turn, size);
            var innerQ = orbitPoint(b, radius - thickness, tilt, turn, size);
            c.globalAlpha = front ? 0.18 + Math.max(0, p[2]) * 0.28 : 0.11;
            c.fillStyle = color;
            c.beginPath(); c.moveTo(p[0], p[1]); c.lineTo(q[0], q[1]);
            c.lineTo(innerQ[0], innerQ[1]); c.lineTo(innerP[0], innerP[1]);
            c.closePath(); c.fill();
            c.globalAlpha = front ? 0.28 + Math.max(0, p[2]) * 0.36 : 0.16;
            c.strokeStyle = highlight; c.lineWidth = Math.max(0.6, size * 0.002);
            c.beginPath(); c.moveTo(p[0], p[1]); c.lineTo(q[0], q[1]); c.stroke();
        }
    }
    c.restore();
}

function currents(context, size, seconds, color) {
    var middle = size / 2;
    context.save();
    context.beginPath();
    context.arc(middle, middle, size * 0.325, 0, Math.PI * 2);
    context.clip();
    context.translate(middle, middle);
    context.strokeStyle = color;
    // Closed irregular arcs travel within the glass; the rim and label stay still.
    for (var band = 0; band < 9; band++) {
        context.globalAlpha = 0.10 + (band % 3) * 0.055;
        context.lineWidth = size * (0.006 + (band % 2) * 0.004);
        context.beginPath();
        for (var step = 0; step <= 64; step++) {
            var angle = step * Math.PI / 32;
            var wave = Math.sin(angle * 3 + seconds * 0.43 + band * 0.72);
            var radius = size * (0.13 + band * 0.019 + 0.018 * wave);
            var rotation = seconds * (0.035 + band * 0.003) + band * 0.28;
            var x = Math.cos(angle + rotation) * radius;
            var y = Math.sin(angle + rotation) * radius * (0.67 + 0.13 * Math.cos(seconds * 0.17 + band));
            if (step === 0) context.moveTo(x, y); else context.lineTo(x, y);
        }
        context.closePath();
        context.stroke();
    }
    context.restore();
}
