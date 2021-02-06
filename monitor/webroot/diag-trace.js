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
    return "diag-trace";
}

/**
 * 
 */
function onLoad() {
    $.get("diag-trace.html", function(data) {
        $('#content-section').html(data);
        var hash = window.location.hash;
        if (hash) {
            var peerId = hash.split('/')[1];
            fetchDiagLog(peerId);
        }
    });
}

/**
 * 
 */
function onRefresh(json) {
    var ellog = $('#diagnostic-log');
    ellog.html('');
    for (var i = 0; i < json.length; i++) {
        var line = json[i];
        ellog.append(line);
    }

    ellog.scrollTop = ellog.scrollHeight;
}
