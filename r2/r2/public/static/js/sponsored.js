function update_box(elem) {
   $(elem).prevAll('*[type="checkbox"]:first').prop('checked', true);
};

function get_ndays($form) {
    return Math.round((Date.parse($form.find('*[name="enddate"]').val()) -
                       Date.parse($form.find('*[name="startdate"]').val())) / (86400*1000))
}

function get_bid($form) {
    return parseFloat($form.find('*[name="bid"]').val())
}

function get_cpm($form) {
    return $form.find('*[name="cpm"]').val()
}

function fill_inputs() {
    var $form = $("#campaign"),
        bid = get_bid($form),
        cpm = get_cpm($form),
        ndays = get_ndays($form),
        impressions = calc_impressions(bid, cpm);

    $(".duration").html(ndays + ((ndays > 1) ? " days" : " day"))
    $(".impression-info").html(pretty_number(impressions) + " impressions")
    $(".price-info").html("$" + (cpm/100).toFixed(2) + " per 1000 impressions")
}

function on_date_change() {
    fill_inputs()
}

function on_bid_change() {
    fill_inputs()
}

function disable_form($form) {
    $form.find('button[name="create"], button[name="save"]')
        .prop("disabled", "disabled")
        .addClass("disabled");
}

function enable_form($form) {
    $form.find('button[name="create"], button[name="save"]')
        .removeProp("disabled")
        .removeClass("disabled");
}

function check_bid() {
    var $form = $("#campaign"),
        bid = get_bid($form),
        minimum_bid = $("#bid").data("min_bid");

    $(".minimum-spend").removeClass("error");
    if (bid < minimum_bid) {
        $(".minimum-spend").addClass("error");
        disable_form($form)
    } else {
        enable_form($form)
    }
}

function update_bid(elem) {
    var form = $(elem).parents(".campaign");
    var is_targeted = $("#targeting").prop("checked");
    var bid = parseFloat(form.find('*[name="bid"]').val());
    var ndays = ((Date.parse(form.find('*[name="enddate"]').val()) -
             Date.parse(form.find('*[name="startdate"]').val())) / (86400*1000));
    ndays = Math.round(ndays);

    // min bid is slightly higher for targeted promos
    var minimum_daily_bid = is_targeted ? $("#bid").data("min_daily_bid") * 1.5 : 
                                          $("#bid").data("min_daily_bid");
    $(".minimum-spend").removeClass("error");
    if (bid < ndays * minimum_daily_bid) {
        $(".bid-info").addClass("error");
        if (is_targeted) {
            $("#targeted_minimum").addClass("error");
        } else {
            $("#no_targeting_minimum").addClass("error");
        }

        form.find('button[name="create"], button[name="save"]')
            .prop("disabled", "disabled")
            .addClass("disabled");
    } else {
        $(".bid-info").removeClass("error");
        form.find('button[name="create"], button[name="save"]')
            .removeProp("disabled")
            .removeClass("disabled");
    }

    $(".bid-info").html("&nbsp; &rarr;" + 
                        "<b>$" + (bid/ndays).toFixed(2) +
         "</b> per day for <b>" + ndays + " day(s)</b>");
 }

var dateFromInput = function(selector, offset) {
   if(selector) {
     var input = $(selector);
     if(input.length) {
        var d = new Date();
        offset = $.with_default(offset, 0);
        d.setTime(Date.parse(input.val()) + offset);
        return d;
     }
   }
};

function attach_calendar(where, min_date_src, max_date_src, callback, min_date_offset) {
     $(where).siblings(".datepicker").mousedown(function() {
            $(this).addClass("clicked active");
         }).click(function() {
            $(this).removeClass("clicked")
               .not(".selected").siblings("input").focus().end()
               .removeClass("selected");
         }).end()
         .focus(function() {
          var target = $(this);
          var dp = $(this).siblings(".datepicker");
          if (dp.children().length == 0) {
             dp.each(function() {
               $(this).datepicker(
                  {
                      defaultDate: dateFromInput(target),
                          minDate: dateFromInput(min_date_src, min_date_offset),
                          maxDate: dateFromInput(max_date_src),
                          prevText: "&laquo;", nextText: "&raquo;",
                          altField: "#" + target.attr("id"),
                          onSelect: function() {
                              $(dp).addClass("selected").removeClass("clicked");
                              $(target).blur();
                              if(callback) callback(this);
                          }
                })
              })
              .addClass("drop-choices");
          };
          dp.addClass("inuse active");
     }).blur(function() {
        $(this).siblings(".datepicker").not(".clicked").removeClass("inuse");
     }).click(function() {
        $(this).siblings(".datepicker.inuse").addClass("active");
     });
}

function check_enddate(startdate, enddate) {
  var startdate = $(startdate)
  var enddate = $(enddate);
  if(dateFromInput(startdate) >= dateFromInput(enddate)) {
    var newd = new Date();
    newd.setTime(startdate.datepicker('getDate').getTime() + 86400*1000);
    enddate.val((newd.getMonth()+1) + "/" +
      newd.getDate() + "/" + newd.getFullYear());
  }
  $("#datepicker-" + enddate.attr("id")).datepicker("destroy");
}

function targeting_on(elem) {
    $(elem).parents(".campaign").find(".targeting")
        .find('*[name="sr"]').prop("disabled", "").end().slideDown();
}

function targeting_off(elem) {
    $(elem).parents(".campaign").find(".targeting")
        .find('*[name="sr"]').prop("disabled", "disabled").end().slideUp();
}

(function($) {

function get_flag_class(flags) {
    var css_class = "campaign-row";
    if(flags.free) {
        css_class += " free";
    }
    if(flags.live) {
        css_class += " live";
    }
    if(flags.complete) {
        css_class += " complete";
    }
    else if (flags.paid) {
            css_class += " paid";
    }
    if (flags.sponsor) {
        css_class += " sponsor";
    }
    return css_class
}

$.new_campaign = function(campaign_id36, start_date, end_date, duration,
                          bid, cpm, speed, targeting, flags) {
    cancel_edit(function() {
      var data =('<input type="hidden" name="startdate" value="' + 
                 start_date +'"/>' + 
                 '<input type="hidden" name="enddate" value="' + 
                 end_date + '"/>' + 
                 '<input type="hidden" name="bid" value="' + bid + '"/>' +
                 '<input type="hidden" name="cpm" value="' + cpm + '"/>' +
                 '<input type="hidden" name="speed" value="' + speed + '"/>' +
                 '<input type="hidden" name="targeting" value="' + 
                 (targeting || '') + '"/>' +
                 '<input type="hidden" name="campaign_id36" value="' + campaign_id36 + '"/>');
      if (flags && flags.pay_url) {
          data += ("<input type='hidden' name='pay_url' value='" + 
                   flags.pay_url + "'/>");
      }
      if (flags && flags.view_live_url) {
          data += ("<input type='hidden' name='view_live_url' value='" + 
                   flags.view_live_url + "'/>");
      }
      var row = [start_date, end_date, duration, "$" + bid, speed, targeting, data];
      $(".existing-campaigns .error").hide();
      var css_class = get_flag_class(flags);
      $(".existing-campaigns table").show()
      .insert_table_rows([{"id": "", "css_class": css_class, 
                           "cells": row}], -1);
      check_number_of_campaigns();
      $.set_up_campaigns()
        });
   return $;
};

$.update_campaign = function(campaign_id36, start_date, end_date,
                             duration, bid, cpm, speed, targeting, flags) {
    cancel_edit(function() {
            $('.existing-campaigns input[name="campaign_id36"]')
                .filter('*[value="' + (campaign_id36 || '0') + '"]')
                .parents("tr").removeClass()
            .addClass(get_flag_class(flags))
                .children(":first").html(start_date)
                .next().html(end_date)
                .next().html(duration)
                .next().html("$" + bid).removeClass()
                .next().html(speed)
                .next().html(targeting)
                .next()
                .find('*[name="startdate"]').val(start_date).end()
                .find('*[name="enddate"]').val(end_date).end()
                .find('*[name="targeting"]').val(targeting).end()
                .find('*[name="bid"]').val(bid).end()
                .find('*[name="cpm"]').val(cpm).end()
                .find('*[name="speed"]').val(speed).end()
                .find("button, span").remove();
            $.set_up_campaigns();
        });
};

$.set_up_campaigns = function() {
    var edit = "<button>edit</button>";
    var del = "<button>delete</button>";
    var pay = "<button>pay</button>";
    var free = "<button>free</button>";
    var repay = "<button>change</button>";
    var view = "<button>view live</button>";
    $(".existing-campaigns tr").each(function() {
            var tr = $(this);
            var td = $(this).find("td:last");
            var bid_td = $(this).find("td:first").next().next().next()
                .addClass("bid");
            if(td.length && ! td.children("button, span").length ) {
                if(tr.hasClass("live")) {
                    $(td).append($(view).addClass("view fancybutton")
                            .click(function() { view_campaign(tr) }));
                }
                /* once paid, we shouldn't muck around with the campaign */
                if(!tr.hasClass("complete")) {
                    if (tr.hasClass("sponsor") && !tr.hasClass("free")) {
                        $(bid_td).append($(free).addClass("free")
                                     .click(function() { free_campaign(tr) }))
                    }
                    else if (!tr.hasClass("paid")) {
                        $(bid_td).prepend($(pay).addClass("pay fancybutton")
                                     .click(function() { pay_campaign(tr) }));
                    } else if (tr.hasClass("free")) {
                        $(bid_td).addClass("free paid")
                            .prepend("<span class='info'>freebie</span>");
                    } else {
                        (bid_td).addClass("paid")
                            .prepend($(repay).addClass("pay fancybutton")
                                     .click(function() { pay_campaign(tr) }));
                    }
                    var e = $(edit).addClass("edit fancybutton")
                        .click(function() { edit_campaign(tr); });
                    var d = $(del).addClass("d fancybutton")
                        .click(function() { del_campaign(tr); });
                    $(td).append(e).append(d);
                }
                else {
                    $(td).append("<span class='info'>complete/live</span>");
                    $(bid_td).addClass("paid")
                    /* sponsors can always edit */
                    if (tr.hasClass("sponsor")) {
                        var e = $(edit).addClass("edit fancybutton")
                            .click(function() { edit_campaign(tr); });
                        $(td).append(e);
                    }
                }
            }
        });
    return $;

}

}(jQuery));

function detach_campaign_form() {
    /* remove datepicker from fields */
    $("#campaign").find(".datepicker").each(function() {
            $(this).datepicker("destroy").siblings().unbind();
        });

    /* detach and return */
    var campaign = $("#campaign").detach();
    return campaign;
}

function cancel_edit(callback) {
    if($("#campaign").parents('tr:first').length) {
        var tr = $("#campaign").parents("tr:first").prev();
        /* copy the campaign element */
        /* delete the original */
        $("#campaign").fadeOut(function() {
                $(this).parent('tr').prev().fadeIn();
                var td = $(this).parent();
                var campaign = detach_campaign_form();
                td.delete_table_row(function() {
                        tr.fadeIn(function() {
                                $(".existing-campaigns").before(campaign);
                                campaign.hide();
                                if(callback) { callback(); }
                            });
                    });
            });
    } else {
        if ($("#campaign:visible").length) {
            $("#campaign").fadeOut(function() {
                    if(callback) { 
                        callback();
                    }});
        }
        else if (callback) {
            callback();
        }
    }
}

function del_campaign(elem) {
    var campaign_id36 = $(elem).find('*[name="campaign_id36"]').val();
    var link_id = $("#campaign").find('*[name="link_id"]').val();
    $.request("delete_campaign", {"campaign_id36": campaign_id36,
                                  "link_id": link_id},
              null, true, "json", false);
    $(elem).children(":first").delete_table_row(check_number_of_campaigns);
}


function edit_campaign(elem) {
    /* find the table row in question */
    var tr = $(elem).get(0);

    if ($("#campaign").parents('tr:first').get(0) != tr) {

        cancel_edit(function() {

            /* copy the campaign element */
            var campaign = detach_campaign_form();

            $(".existing-campaigns table")
                .insert_table_rows([{"id": "edit-campaign-tr",
                                "css_class": "", "cells": [""]}], 
                    tr.rowIndex + 1);
            $("#edit-campaign-tr").children('td:first')
                .attr("colspan", 7).append(campaign).end()
                .prev().fadeOut(function() { 
                        var data_tr = $(this);
                        var c = $("#campaign");
                        $.map(['startdate', 'enddate', 'bid', 'cpm', 'campaign_id36'],
                              function(i) {
                                  i = '*[name="' + i + '"]';
                                  c.find(i).val(data_tr.find(i).val());
                              });
                        /* check speed */
                        var speed = data_tr.find('*[name="speed"]').val(),
                            speed_radios = c.find('*[name="speed"]');
                        speed_radios.filter('*[value="' + speed + '"]').prop("checked", "checked")

                        /* check if targeting is turned on */
                        var targeting = data_tr
                            .find('*[name="targeting"]').val();
                        var radios=c.find('*[name="targeting"]');
                        if (targeting) {
                            radios.filter('*[value="one"]')
                                .prop("checked", "checked");
                            c.find('*[name="sr"]').val(targeting).prop("disabled", "").end()
                                .find(".targeting").show();
                        }
                        else {
                            radios.filter('*[value="none"]')
                                .prop("checked", "checked");
                            c.find('*[name="sr"]').val("").prop("disabled", "disabled").end()
                                .find(".targeting").hide();
                        }
                        /* attach the dates to the date widgets */
                        init_startdate();
                        init_enddate();
                        c.find('button[name="save"]').show().end()
                            .find('button[name="create"]').hide().end();
                        fill_inputs();
                        check_bid();
                        c.fadeIn();
                    } );
            }
            );
    }
}

function check_number_of_campaigns(){
    if ($(".campaign-row").length >= $(".existing-campaigns").data("max-campaigns")){
      $(".error.TOO_MANY_CAMPAIGNS").fadeIn();
      $("button.new-campaign").attr("disabled", "disabled");
      return true;
    } else {
      $(".error.TOO_MANY_CAMPAIGNS").fadeOut();
      $("button.new-campaign").removeAttr("disabled");
      return false;
    }
}

function create_campaign(elem) {
    if (check_number_of_campaigns()){
        return;
    }
    cancel_edit(function() {;
            var base_cpm = $("#bid").data("base_cpm")
            init_startdate();
            init_enddate();
            $("#campaign")
                .find('button[name="edit"]').hide().end()
                .find('button[name="create"]').show().end()
                .find('input[name="campaign"]').val('').end()
                .find('input[name="sr"]').val('').end()
                .find('input[name="targeting"][value="none"]')
                                .prop("checked", "checked").end()
                .find(".targeting").hide().end()
                .find('*[name="sr"]').val("").prop("disabled", "disabled").end()
                .find('input[name="cpm"]').val(base_cpm).end()
                .fadeIn();
            on_date_change();
        });
}

function free_campaign(elem) {
    var campaign_id36 = $(elem).find('*[name="campaign_id36"]').val();
    var link_id = $("#campaign").find('*[name="link_id"]').val();
    $.request("freebie", {"campaign_id36": campaign_id36, "link_id": link_id},
              null, true, "json", false);
    $(elem).find(".free").fadeOut();
    return false; 
}

function pay_campaign(elem) {
    $.redirect($(elem).find('input[name="pay_url"]').val());
}

function view_campaign(elem) {
    $.redirect($(elem).find('input[name="view_live_url"]').val());
}

function pretty_number(number) {
    var numberAsInt = parseInt(number)
    if (numberAsInt) {
        return numberAsInt.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")
    } else {
        return number
    }
}

function calc_impressions(bid, cpm_pennies) {
    return bid / cpm_pennies * 1000 * 100
}
