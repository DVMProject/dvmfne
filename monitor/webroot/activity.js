/**
 * Digital Voice Modem - Fixed Network Equipment
 * GPLv2 Open Source. Use is subject to license terms.
 * DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
 *
 * @package DVM / FNE
 */

var actFirstRefresh = true;

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

        onRefresh();
    });
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

/**
 * 
 */
function refreshActivity() {
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
        return '<span class="span-' + row.type_class + '">' + value + '</span>';
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
            classes: "col-danger"
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
function actDurationCellStyle(value, row, index) {
    if (value === 'Timing unavailable') {
        return {
            classes: "col-disabled"
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
            classes: "col-disabled"
        };
    } else {
        if (value >= 0.0 && value <= 1.9) {
            return {
                classes: "col-success"
            };
        }
        else if ((value >= 2.0) && (value <= 2.9)) {
            return {
                classes: "col-warn"
            };
        }
        else if (value >= 3.0) {
            return {
                classes: "col-danger"
            };
        }
        else {
            return {};
        }
    }
}
