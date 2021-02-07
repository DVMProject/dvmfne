/**
 * Digital Voice Modem - Fixed Network Equipment
 * GPLv2 Open Source. Use is subject to license terms.
 * DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
 *
 * @package DVM / FNE
 */

/*
** Page View Routines
*/

/**
 * 
 * @returns {any} string
 */
function getInfo() {
    return "traffic-trace";
}

/**
 * 
 */
function onLoad() {
    $.get("traffic-trace.html", function(data) {
        $('#content-section').html(data);
        onRefresh();
    });
}

/**
 * 
 */
function onUnload() {
    /* stub */
}

/**
 * 
 */
function onRefresh() {
    var log = $('#traffic-trace-log');

    var content = '';
    for (var i = 0; i < trafficTrace.length; i++) {
        content += trafficTrace[i] + '\n';
    }

    log.html(content);
}
