/**
 * Digital Voice Modem - Fixed Network Equipment
 * GPLv2 Open Source. Use is subject to license terms.
 * DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
 *
 * @package DVM / FNE
 */

var pageLoaded = false;

var NO_SYSTEM_SEL = 'No system(s) selected for remote command!';
var COMMAND_NOT_CONFIRMED = 'Command was not confirmed! Cowardly refusing to transmit!';

var rconCommand = '';
var rconDmrSlot = 0;
var commandConfirmed = true;

/*
** Page View Routines
*/

/**
 * 
 * @returns {any} string
 */
function getInfo() {
    return "rcon";
}

/**
 * 
 */
function onLoad() {
    $.get("rcon.html", function(data) {
        $('#content-section').html(data);
        $('#refresh').click(function () {
            refreshSystems();
        });

        $('#cmd_send_btn').click(function () {
            rconTransmit();
        });

        $("#cmd_confirm_check").change(function () {
            if (this.checked) {
                commandConfirmed = true;
                $('#cmd_send_btn').removeProp('disabled');
            } else {
                commandConfirmed = false;
                $('#cmd_send_btn').prop('disabled', 'disabled');
            }
        });

        rconResetConfirm();
        rconSetDmrSlot(1);
        $('#cmd_send_btn').prop('disabled', 'disabled');
        $('#dmr_slot_sel').hide();
        $('#mot_mfid_check').hide();

        showTableLoading('#master-systems');
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
    if (!$.isEmptyObject(config) && !pageLoaded) {
        refreshSystems();
        pageLoaded = true;
    }
}

/*
** Private Routines
*/

/**
 * 
 */
function refreshSystems() {
    showTableLoading('#master-systems');

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
                    'ipAddr': value.IP,
                    'ipPort': value.PORT,
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
    } else {
        // populate bootstrap table
        $('#master-systems').bootstrapTable("destroy");
        $('#master-systems').bootstrapTable({
            data: []
        });
    }
}

/**
 * 
 */
function rconResetConfirm() {
    $('#cmd_confirm').hide();
    $('#cmd_confirm_check').prop("checked", true);
    commandConfirmed = true;
    $('#cmd_send_btn').removeProp('disabled');
}

/**
 * 
 */
function rconSetConfirm() {
    $('#cmd_confirm').show();
    $('#cmd_confirm_check').prop("checked", false);
    commandConfirmed = false;
    $('#cmd_send_btn').prop('disabled', 'disabled');
}

/**
 * 
 * @param {any} command
 * @param {any} label
 */
function rconSetCmd(command, label) {
    rconCommand = command;

    $('#cmd_sel_label').html(label);
    $('#cmd_argument').removeProp('disabled');
    $('#cmd_mot_mfid').removeProp('disabled');
    $('#cmd_mot_mfid').prop("checked", false);

    if (command.startsWith('dmr')) {
        $('#dmr_slot_sel').show();
    } else {
        $('#dmr_slot_sel').hide();
    }

    if (command.startsWith('p25')) {
        $('#mot_mfid_check').show();
    } else {
        $('#mot_mfid_check').hide();
    }

    // setup confirmation for confirmed commands...
    switch (rconCommand) {
        case 'p25-cc':
        case 'dmr-beacon':
        case 'p25-cc-bcast':
        case 'p25-cc-dedicated':
        case 'p25-en-dump-tsbk':
        case 'p25-dis-dump-tsbk':
        case 'p25-en-debug':
        case 'p25-dis-debug':
        case 'dmr-en-debug':
        case 'dmr-dis-debug':
        case 'dynamic-mode':
        case 'dmr-mode':
        case 'p25-mode':
            $('#dmr_slot_sel').hide();
            $('#cmd_argument').prop('disabled', 'disabled');
            $('#mot_mfid_check').hide();
            $('#cmd_mot_mfid').prop('disabled', 'disabled');
            rconResetConfirm();
            break;

        case 'p25-rid-inhibit':
        case 'p25-rid-uninhibit':
        case 'dmr-rid-inhibit':
        case 'dmr-rid-uninhibit':
            rconSetConfirm();
            break;

        case 'p25-rel-grnts':
        case 'p25-rel-affs':
            $('#cmd_argument').prop('disabled', 'disabled');
            $('#mot_mfid_check').hide();
            $('#cmd_mot_mfid').prop('disabled', 'disabled');
            rconSetConfirm();
            break;

        default:
            rconResetConfirm();
            break;
    }
}

/**
 * 
 * @param {any} slot
 */
function rconSetDmrSlot(slot) {
    rconDmrSlot = slot;
    $('#cmd_dmr_slot_label').html('Slot ' + slot);
}

/**
 * 
 */
function rconTransmit() {
    if (commandConfirmed) {
        var argument = $('#cmd_argument').val();
        var motMfId = $("#cmd_mot_mfid").is(':checked');

        switch (rconCommand) {
            case 'p25-en-dump-tsbk':
                rconCommand = 'p25-dump-tsbk';
                argument = '1';
                break;
            case 'p25-dis-dump-tsbk':
                rconCommand = 'p25-dump-tsbk';
                argument = '0';
                break;

            case 'p25-en-debug':
                rconCommand = 'p25-debug';
                argument = '1 1';
                break;
            case 'p25-dis-debug':
                rconCommand = 'p25-debug';
                argument = '0 1';
                break;

            case 'dmr-en-debug':
                rconCommand = 'dmr-debug';
                argument = '1 1';
                break;
            case 'dmr-dis-debug':
                rconCommand = 'dmr-debug';
                argument = '0 1';
                break;

            case 'dynamic-mode':
                rconCommand = 'mdm-mode';
                argument = 'idle';
                break;
            case 'dmr-mode':
                rconCommand = 'mdm-mode';
                argument = 'dmr';
                break;
            case 'p25-mode':
                rconCommand = 'mdm-mode';
                argument = 'p25';
                break;
        }

        // get the selected systems
        var systemSelections = $('#master-systems').bootstrapTable('getSelections');
        if (systemSelections.length === 0) {
            displayErrorAlert(NO_SYSTEM_SEL);
            return;
        }

        for (var i = 0; i < systemSelections.length; i++) {
            var peerId = systemSelections[i].peerId;
            transmitCommand(peerId, rconCommand, rconDmrSlot, motMfId, argument);
        }
    } else {
        displayErrorAlert(COMMAND_NOT_CONFIRMED);
    }
}
