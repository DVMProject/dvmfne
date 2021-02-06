/**
 * Digital Voice Modem - Fixed Network Equipment
 * GPLv2 Open Source. Use is subject to license terms.
 * DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
 *
 * @package DVM / FNE
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
function onRefresh() {
    var ellog = $('#traffic-trace-log');
    ellog.html(trafficTrace);
    ellog.scrollTop = ellog.scrollHeight;
}
