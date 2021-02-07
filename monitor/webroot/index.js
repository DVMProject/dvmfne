/**
 * Digital Voice Modem - Fixed Network Equipment
 * GPLv2 Open Source. Use is subject to license terms.
 * DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
 *
 * @package DVM / FNE
 */

var sock = null;
var wsport = 9000;

var WEBSOCK_OPCODES = {
    'QUIT': 'q',
    'CONFIG': 'c',
    'RULES': 'r',
    'AFFILIATION': 'g',
    'ACTIVITY': 'a',
    'LOG': 'l',
    'DIAG_LOG': 'd',
    'MESSAGE': 'm'
};

var config = {};
var rules = {};
var affiliations = {};
var activity = {};

var trafficTrace = [];
var trafficTraceMaxLines = 65535;

var peerMap = {};

var exclamationIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-exclamation-octagon" viewBox="0 0 16 16">' +
    '<path d="M4.54.146A.5.5 0 0 1 4.893 0h6.214a.5.5 0 0 1 .353.146l4.394 4.394a.5.5 0 0 1 .146.353v6.214a.5.5 0 0 1-.146.353l-4.394 4.394a.5.5 0 0 1-.353.146H4.893a.5.5 0 0 1-.353-.146L.146 11.46A.5.5 0 0 1 0 11.107V4.893a.5.5 0 0 1 .146-.353L4.54.146zM5.1 1L1 5.1v5.8L5.1 15h5.8l4.1-4.1V5.1L10.9 1H5.1z" />' +
    '<path d="M7.002 11a1 1 0 1 1 2 0 1 1 0 0 1-2 0zM7.1 4.995a.905.905 0 1 1 1.8 0l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 4.995z" />' +
    '</svg>';
var checkIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-check2-circle" viewBox="0 0 16 16">' +
    '<path d="M2.5 8a5.5 5.5 0 0 1 8.25-4.764.5.5 0 0 0 .5-.866A6.5 6.5 0 1 0 14.5 8a.5.5 0 0 0-1 0 5.5 5.5 0 1 1-11 0z"/>' +
    '<path d="M15.354 3.354a.5.5 0 0 0-.708-.708L8 9.293 5.354 6.646a.5.5 0 1 0-.708.708l3 3a.5.5 0 0 0 .708 0l7-7z"/>' +
    '</svg>';
var errorIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-x-octagon" viewBox="0 0 16 16">' +
    '<path d="M4.54.146A.5.5 0 0 1 4.893 0h6.214a.5.5 0 0 1 .353.146l4.394 4.394a.5.5 0 0 1 .146.353v6.214a.5.5 0 0 1-.146.353l-4.394 4.394a.5.5 0 0 1-.353.146H4.893a.5.5 0 0 1-.353-.146L.146 11.46A.5.5 0 0 1 0 11.107V4.893a.5.5 0 0 1 .146-.353L4.54.146zM5.1 1L1 5.1v5.8L5.1 15h5.8l4.1-4.1V5.1L10.9 1H5.1z"/>' +
    '<path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>' +
    '</svg>';

/**
 * 
 * @param {any} scriptName
 */
function loadScript(scriptName) {
    if (typeof onUnload === "function") {
        onUnload();
    }
    $.getScript(scriptName)
        .done(function (script, textStatus) {
            console.log("Active view:", getInfo());
            onLoad();
        }).fail(function (jqxhr, settings, exception) {
            console.error("ajaxError:", jqxhr, exception);
        });
}

/**
 * 
 * @param {any} hash
 */
function displayHash(hash) {
    if (hash) {
        if (hash.includes('/')) {
            hash = hash.split('/')[0];
        }

        // assumes that the anchor tag and li tag
        // remove the current anchor tag
        $(".active").removeClass("active");
        $('a[href="' + hash + '"]').addClass("active");

        loadScript(hash.replace("#", "") + ".js");
    }
}

/**
 * 
 * @param {any} value
 * @returns {any} value 
 */
function boldFormatter(value) {
    return '<b>' + value + '</b>';
}

/**
 * 
 * @param {any} value
 * @returns {any} value 
 */
function freqFormatter(value) {
    var mhzFreq = value / 1000000;
    mhzFreq = mhzFreq.toFixed(5);

    return mhzFreq + ' MHz';
}

/**
 * 
 * @param {any} value
 * @returns {any} value 
 */
function trueFalseFormatter(value) {
    if (value === 'True') {
        // check icon
        return '<div align="center">' + checkIcon + '</div>';
    } else {
        // X icon
        return '<div align="center">' + errorIcon + '</div>';
    }
}

/**
 * 
 * @param {any} value
 * @param {any} row 
 * @param {any} index 
 * @returns {any} value
 */
function trueFalseCellStyle(value, row, index) {
    if (value !== "True") {
        // HACK: let this support YES values too
        if (value === 'YES') {
            return {
                classes: "table-success"
            };
        }

        return {
            classes: "table-danger"
        };
    } else {
        return {
            classes: "table-success"
        };
    }
}

/**
 * 
 * @param {any} peerId
 * @param {any} type
 * @param {any} slotNo
 * @param {any} motMFId
 * @param {any} argument
 */
function transmitCommand(peerId, type, slotNo, motMFId, argument) {
    if (!type.startsWith('dmr')) {
        slotNo = 0; // force to 0
    }

    if (sock) {
        sock.send(WEBSOCK_OPCODES.MESSAGE + peerId + ',' + type + ',' + argument + ',' + slotNo + ',' + motMFId);
    }
}

/**
 * 
 * @param {any} peerId
 */
function fetchDiagLog(peerId) {
    if (sock) {
        sock.send(WEBSOCK_OPCODES.DIAG_LOG + peerId);
    }
}

$(document).ready(function () {
    $('#diag-trace-nav').hide();

    if (window.location.hash) {
        displayHash(window.location.hash);
    }
    else {
        loadScript('overview.js');
    }

    $(window).on('hashchange', function () {
        // on every hash change the render function is called with the new hash
        displayHash(window.location.hash);
    });

    var wsuri = "ws://" + window.location.hostname + ":" + wsport;
    if ("WebSocket" in window) {
        sock = new WebSocket(wsuri);
    } else if ("MozWebSocket" in window) {
        sock = new MozWebSocket(wsuri);
    } else {
        console.error("Browser does not support WebSocket!");
    }

    if (sock) {
        sock.onopen = function () {
            $('#no-connection').hide();
            console.log("Connected to " + wsuri);
        };

        sock.onclose = function (e) {
            $('#no-connection').show();
            console.log("Connection closed (wasClean = " + e.wasClean + ", code = " + e.code + ", reason = '" + e.reason + "')");
            sock = null;
        };

        sock.onmessage = function (e) {
            var opcode = e.data.slice(0, 1);
            var message = e.data.slice(1);

            //console.debug(opcode, message);

            if (opcode === WEBSOCK_OPCODES['QUIT']) {
                $('#no-connection').show();

                config = {};
                rules = {};
                talkgroups = {};
                activity = {};
            }
            else if (opcode === WEBSOCK_OPCODES['CONFIG']) {
                config = JSON.parse(message);

                if (!$.isEmptyObject(config)) {
                    peerMap = {};
                    $.each(config.MASTERS, function (key, value) {
                        var masterPeers = value.PEERS;
                        $.each(masterPeers, function (key, value) {
                            var peerId = key;
                            var peerName = value.IDENTITY;
                            peerMap[peerId] = peerName;
                        });
                    });
                }
            }
            else if (opcode === WEBSOCK_OPCODES['RULES']) {
                rules = JSON.parse(message);
            }
            else if (opcode === WEBSOCK_OPCODES['AFFILIATION']) {
                affiliations = JSON.parse(message);
            }
            else if (opcode === WEBSOCK_OPCODES['ACTIVITY']) {
                activity = JSON.parse(message);
            }
            else if (opcode === WEBSOCK_OPCODES['LOG']) {
                trafficTrace.reverse();
                if (trafficTrace.length >= trafficTraceMaxLines) {
                    trafficTrace.splice(0, 1);
                }

                trafficTrace.push(message);
                trafficTrace.reverse();
            }
            else if (opcode === WEBSOCK_OPCODES['DIAG_LOG']) {
                /* ignore */
            } else {
                console.error("Unknown Message Received", opcode, message);
            }

            if (getInfo() === 'overview' && (opcode === WEBSOCK_OPCODES['CONFIG'] || opcode === WEBSOCK_OPCODES['AFFILIATION'])) {
                onRefresh();
            }

            if (getInfo() === 'activity' && opcode === WEBSOCK_OPCODES['ACTIVITY']) {
                onRefresh();
            }

            if (getInfo() === 'traffic-trace' && opcode === WEBSOCK_OPCODES['LOG']) {
                onRefresh();
            }

            if (getInfo() === 'diag-trace' && opcode === WEBSOCK_OPCODES['DIAG_LOG']) {
                onRefresh(JSON.parse(message));
            }
        };
    }
});
