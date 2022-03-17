/**
 * Digital Voice Modem - Fixed Network Equipment
 * GPLv2 Open Source. Use is subject to license terms.
 * DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
 *
 * @package DVM / FNE
 */

var affFirstRefresh = true;

/*
** Page View Routines
*/

/**
 * 
 * @returns {any} value
 */
function getInfo() {
    return "overview";
}

/**
 * 
 */
function onLoad() {
    $.get("overview.html", function(data) {
        $('#content-section').html(data);
        $('#aff-auto-refresh').prop("checked", true);
        $('#aff-refresh').click(function () {
            refreshAffiliations();
        });

        showTableLoading('#master-systems');
        showTableLoading('#peer-systems');
        showTableLoading('#affiliations');
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
    if (!$.isEmptyObject(config)) {
        var masterData = [];

        // iterate over masters
        var masters = config.MASTERS;
        $.each(masters, function (key, value) {
            var masterName = key;
            var masterPeers = value.PEERS;
            $.each(masterPeers, function (key, value) {
                var peerId = key;
                masterData.push({
                    'masterName': masterName,
                    'peerId': peerId,
                    'identity': value.IDENTITY,
                    'rxFreq': value.RX_FREQ,
                    'txFreq': value.TX_FREQ,
                    'channelId': value.CHANNEL_ID,
                    'channelNo': value.CHANNEL_NO,
                    'latitude': value.LATITUDE,
                    'longitude': value.LONGITUDE,
                    'height': value.HEIGHT,
                    'ipAddr': value.IP,
                    'ipPort': value.PORT,
                    'pings': value.PINGS_RECEIVED,
                    'connection': value.CONNECTION,
                    'software': value.SOFTWARE_ID
                });
            });
        });

        // populate bootstrap table
        $('#master-systems').bootstrapTable("destroy");
        $('#master-systems').bootstrapTable({
            data: masterData
        });

        var peerData = [];

        // iterate over peers
        var peers = config.PEERS;
        $.each(peers, function (key, value) {
            var peerName = key;
            peerData.push({
                'peerName': peerName,
                'peerId': value.PEER_ID,
                'identity': value.IDENTITY,
                'rxFreq': value.RX_FREQ,
                'txFreq': value.TX_FREQ,
                'latitude': value.LATITUDE,
                'longitude': value.LONGITUDE,
                'masterIp': value.MASTER_IP,
                'pingSent': value.STATS.PINGS_SENT,
                'pingAck': value.STATS.PINGS_ACKD,
                'connection': value.STATS.CONNECTION
            });
        });

        // populate bootstrap table
        $('#peer-systems').bootstrapTable("destroy");
        $('#peer-systems').bootstrapTable({
            data: peerData
        });
    } else {
        // populate bootstrap table
        $('#master-systems').bootstrapTable("destroy");
        $('#master-systems').bootstrapTable({
            data: []
        });
        $('#master-systems').bootstrapTable("showLoading");

        // populate bootstrap table
        $('#peer-systems').bootstrapTable("destroy");
        $('#peer-systems').bootstrapTable({
            data: []
        });
        $('#peer-systems').bootstrapTable("showLoading");
    }

    var autoRefreshAff = $('#aff-auto-refresh').prop("checked");
    if (autoRefreshAff || affFirstRefresh) {
        affFirstRefresh = false;
        refreshAffiliations();
    }
}

/*
** Private Routines
*/

/**
 *
 */
function refreshAffiliations() {
    if (!$.isEmptyObject(affiliations)) {
        var affiliationData = [];

        // iterate over affiliations
        $.each(affiliations, function (key, value) {
            var fromId = key;
            affiliationData.push({
                'peerId': value.PEER_ID,
                'from': fromId,
                'to': value.DST_ID
            });
        });

        // populate bootstrap table
        $('#affiliations').bootstrapTable("destroy");
        $('#affiliations').bootstrapTable({
            data: affiliationData
        });
    } else {
        // populate bootstrap table
        $('#affiliations').bootstrapTable("destroy");
        $('#affiliations').bootstrapTable({
            data: []
        });
    }
}

/**
 * 
 * @param {any} value
 * @returns {any} value 
 */
function peerIdFormatter(value) {
    return '<a href="#diag-trace/' + value + '">' + value + '</a>';
}
