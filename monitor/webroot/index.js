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

var trafficTrace = '';
var trafficTraceLines = 0;
var trafficTraceMaxLines = 65535;

var peerMap = {};

/**
 * 
 * @param {any} scriptName
 */
function loadScript(scriptName) {
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
        // assumes that the anchor tag and li tag 
        // remove the current anchor tag
        $(".active").removeClass("active");
        $('a[href="' + hash + '"]').parent().addClass("active");

        if (hash.includes('/')) {
            hash = hash.split('/')[0];
            loadScript(hash.replace("#", "") + ".js");
        }
        else {
            loadScript(hash.replace("#", "") + ".js");
        }
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

    return mhzFreq + ' mhz';
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
                            var peerName = value.CALLSIGN;
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
                if (trafficTraceLines >= trafficTraceMaxLines) {
                    trafficTraceLines = 0;
                    trafficTrace = '';
                }

                trafficTrace += message + '\n';
                trafficTraceLines++;
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
