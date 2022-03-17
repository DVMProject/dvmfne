/**
 * Digital Voice Modem - Fixed Network Equipment
 * GPLv2 Open Source. Use is subject to license terms.
 * DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
 *
 * @package DVM / FNE
 */

var actFirstRefresh = true;

/*
** Page View Routines
*/

/**
 * 
 * @returns {any} string
 */
function getInfo() {
    return "activity";
}

/**
 * 
 */
function onLoad() {
    $.get("activity.html", function(data) {
        $('#content-section').html(data);
        $('#act-auto-refresh').prop("checked", true);
        $('#act-refresh').click(function () {
            refreshActivity();
        });

        showTableLoading('#activity');
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
    var autoRefresh = $('#act-auto-refresh').prop("checked");

    // populate bootstrap table
    if (autoRefresh || actFirstRefresh) {
        actFirstRefresh = false;
        refreshActivity();
    }
}

/*
** Private Routines
*/

/**
 * 
 */
function refreshActivity() {
    showTableLoading('#activity');

    // parse data
    if (!$.isEmptyObject(activity)) {
        $('#activity').bootstrapTable("destroy");
        $('#activity').bootstrapTable({
            data: activity
        });
    } else {
        // populate bootstrap table
        $('#activity').bootstrapTable({
            data: []
        });
    }
}

/**
 * 
 * @param {any} value
 * @param {any} row 
 * @returns {any} value
 */
function actTypeFormatter(value, row) {
    if (row.type_class !== 'normal') {
        return '<span class="text-' + row.type_class + '">' + value + '</span>';
    } else {
        return value;
    }
}

/**
 * 
 * @param {any} value
 * @param {any} row 
 * @param {any} index 
 * @returns {any} value
 */
function actTypeCellStyle(value, row, index) {
    if (row.type_class === 'danger') {
        return {
            classes: 'table-danger'
        };
    } else {
        if (row.alert_class !== '') {
            return {
                classes: 'table-' + row.alert_class
            }
        }

        return {};
    }
}

/**
 * 
 * @param {any} value
 * @param {any} row 
 * @param {any} index 
 * @returns {any} value
 */
function actDurationCellStyle(value, row, index) {
    if (value === 'Timing unavailable') {
        return {
            classes: 'table-disabled'
        };
    } else {
        return {};
    }
}

/**
 * 
 * @param {any} value
 * @param {any} row 
 * @param {any} index 
 * @returns {any} value
 */
function actBERCellStyle(value, row, index) {
    if (value === 'No BER data') {
        return {
            classes: 'table-disabled'
        };
    } else {
        if (value >= 0.0 && value <= 1.9) {
            return {
                classes: 'table-success'
            };
        }
        else if (value >= 2.0 && value <= 2.9) {
            return {
                classes: 'table-warning'
            };
        }
        else if (value >= 3.0) {
            return {
                classes: 'table-danger'
            };
        }
        else {
            return {};
        }
    }
}

/**
 * 
 * @param {any} value
 * @returns {any} value 
 */
function peerIdFormatter(value) {
    if (value in peerMap) {
        return peerMap[value] + ' (<i>' + value + '</i>)';
    }
    else {
        return value;
    }
}

/**
 * 
 * @param {any} value
 * @param {any} row
 * @param {any} index
 * @returns {any} value
 */
function srcIdFormatter(value, row, index) {
    if (value === 'SYSTEM') {
        return value;
    }

    if (whitelist_rid.length > 0) {
        var rid = parseInt(value);
        if (rid === NaN) {
            return value;
        }

        if (!whitelist_rid.includes(rid)) {
            return '<span class="text-danger">' + value + '</span>';
        } else {
            return value;
        }
    }

    return value;
}
