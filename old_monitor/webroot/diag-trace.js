/**
 * Digital Voice Modem - Fixed Network Equipment
 * GPLv2 Open Source. Use is subject to license terms.
 * DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
 *
 * @package DVM / FNE
 */

var peerId = 0;
var refreshEvent = {};

var REFRESH_INTERVAL = 10000; // 10 sec

/*
** Page View Routines
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
    $.get("diag-trace.html", function (data) {
        $('#diag-trace-nav').show();

        $('#diag-auto-refresh').prop("checked", false);
        $('#diag-refresh').click(function () {
            fetchDiagLog(peerId);
        });

        refreshEvent = window.setInterval(autoRefreshEvent, REFRESH_INTERVAL);

        $('#content-section').html(data);
        var hash = window.location.hash;
        if (hash) {
            peerId = hash.split('/')[1];

            $('#diag-trace-link').attr('href', '#diag-trace/' + peerId);
            if (peerId in peerMap) {
                $('#peerId').html(peerMap[peerId] + '(<i>' + peerId + '</i>)');
            }
            else {
                $('#peerId').html('<i>' + peerId + '</i>');
            }

            fetchDiagLog(peerId);
        }
    });
}

/**
 * 
 */
function onUnload() {
    $('#diag-trace-nav').hide();
    $('#diag-trace-link').attr('href', '#diag-trace');
    window.clearInterval(refreshEvent);
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

/**
 * 
 */
function autoRefreshEvent() {
    var autoRefresh = $('#diag-auto-refresh').prop("checked");

    // populate bootstrap table
    if (autoRefresh) {
        fetchDiagLog(peerId);
    }
}
