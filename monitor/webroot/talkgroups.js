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
    return "talkgroups";
}

/**
 * 
 */
function onLoad() {
    $.get("talkgroups.html", function(data) {
        $('#content-section').html(data);

        showTableLoading('#talkgroups');
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
    // parse data
    if (!$.isEmptyObject(rules)) {
        var rulesData = [];

        // iterate over rules
        $.each(rules, function (key, value) {
            var srcSystem = key;
            for (var i = 0; i < value.length; i++) {
                var data = value[i];
                var ignored = '';
                for (var j = 0; j < data.IGNORED.length; j++) {
                    var peerId = data.IGNORED[j];
                    if (peerId === 0) {
                        ignored += 'ALL, ';
                    } else {
                        if (peerId in peerMap) {
                            ignored += peerMap[peerId] + ', ';
                        }
                        else {
                            ignored += peerId + ', ';
                        }
                    }
                }
                ignored = ignored.replace(/,\s*$/, "");

                rulesData.push({
                    'srcSystem': srcSystem,
                    'tgName': data.NAME,
                    'srcTGID': data.SRC_GROUP,
                    'srcSlot': data.SRC_TS,
                    'active': data.ACTIVE,
                    'routable': data.ROUTABLE,
                    'dstSystem': data.DST_NET,
                    'dstTGID': data.DST_GROUP,
                    'dstSlot': data.DST_TS,
                    'routeTimeout': data.TIMEOUT,
                    'timeoutAction': data.TO_TYPE,
                    'affRepeated': data.AFFILIATED,
                    'ignoredPeers': ignored
                });
            }
        });

        // populate bootstrap table
        $('#talkgroups').bootstrapTable("destroy");
        $('#talkgroups').bootstrapTable({
            data: rulesData
        });
    } else {
        // populate bootstrap table
        $('#talkgroups').bootstrapTable("destroy");
        $('#talkgroups').bootstrapTable({
            data: []
        });
        $('#talkgroups').bootstrapTable("showLoading");
    }
}
