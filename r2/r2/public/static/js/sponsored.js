r.sponsored = {
  init: function() {
    $("#sr-autocomplete").on("sr-changed blur", function() {
      this.check_impressions()
    })
  },

  setup: function(daily_impressions) {
    this.daily_impressions = daily_impressions
  },

  get_ndays: function($form) {
    return Math.round((Date.parse($form.find('*[name="enddate"]').val()) -
                       Date.parse($form.find('*[name="startdate"]').val())) / (86400*1000))
  },

  get_bid: function($form) {
      return parseFloat($form.find('*[name="bid"]').val())
  },

  get_cpm: function($form) {
      return parseInt($form.find('*[name="cpm"]').val())
  },

  fill_inputs: function() {
      var $form = $("#campaign"),
          bid = this.get_bid($form),
          cpm = this.get_cpm($form),
          ndays = this.get_ndays($form),
          impressions = this.calc_impressions(bid, cpm);

      $(".duration").html(ndays + ((ndays > 1) ? " days" : " day"))
      $(".price-info").html("$" + (cpm/100).toFixed(2) + " per 1000 impressions")

      this.check_impressions()
  },

  get_daily_impressions: function(srname) {
    return this.daily_impressions[srname] || $.ajax({
        type: 'GET',
        url: '/api/daily_impressions.json',
        data: {
            sr: srname
        },
        success: function(data) {
          this.daily_impressions[srname] = data.daily_impressions
        }
      }).pipe(function(data) {
        return data.daily_impressions
      })
  },

  check_impressions: function() {
    var $campaign = $('#campaign'),
        bid = this.get_bid($campaign),
        cpm = this.get_cpm($campaign),
        requested = this.calc_impressions(bid, cpm),
        startdate = $campaign.find('*[name="startdate"]').val(),
        enddate = $campaign.find('*[name="enddate"]').val(),
        ndays = this.get_ndays($campaign),
        targeted = $campaign.find('#targeting').attr('checked') == 'checked',
        target = $campaign.find('*[name="sr"]').val(),
        srname = targeted ? target : ''

    $.when(this.get_daily_impressions(srname)).done(function(daily_impressions) {
      var predicted = ndays * daily_impressions,
          message = r.sponsored.pretty_number(requested) + " impressions"

      console.log('requested: ' + requested + ' predicted: ' + predicted)

      if (predicted < requested) {
        message += "<br>NOTE: Only " + r.sponsored.pretty_number(predicted)
        message += " impressions expected for your selected target and dates."
        message += " To spend your entire budget consider extending the"
        message += " duration or trying a new target."
      }
      $(".impression-info").html(message).show()
    })
  },

  on_date_change: function() {
      this.fill_inputs()
  },

  on_bid_change: function() {
      this.fill_inputs()
  },

  disable_form: function($form) {
      $form.find('button[name="create"], button[name="save"]')
          .prop("disabled", "disabled")
          .addClass("disabled");
  },

  enable_form: function($form) {
      $form.find('button[name="create"], button[name="save"]')
          .removeProp("disabled")
          .removeClass("disabled");
  },

  check_bid: function() {
      var $form = $("#campaign"),
          bid = this.get_bid($form),
          minimum_bid = $("#bid").data("min_bid");

      $(".minimum-spend").removeClass("error");
      if (bid < minimum_bid) {
          $(".minimum-spend").addClass("error");
          this.disable_form($form)
      } else {
          this.enable_form($form)
      }
  },

  dateFromInput: function(selector, offset) {
     if(selector) {
       var input = $(selector);
       if(input.length) {
          var d = new Date();
          offset = $.with_default(offset, 0);
          d.setTime(Date.parse(input.val()) + offset);
          return d;
       }
     }
  },

  pretty_number: function(number) {
      var numberAsInt = parseInt(number)
      if (numberAsInt) {
          return numberAsInt.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")
      } else {
          return number
      }
  },

  calc_impressions: function(bid, cpm_pennies) {
      return bid / cpm_pennies * 1000 * 100
  },

  attach_calendar: function(where, min_date_src, max_date_src, callback, min_date_offset) {
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
                        defaultDate: r.sponsored.dateFromInput(target),
                            minDate: r.sponsored.dateFromInput(min_date_src, min_date_offset),
                            maxDate: r.sponsored.dateFromInput(max_date_src),
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
  },

  check_enddate: function(startdate, enddate) {
    var startdate = $(startdate)
    var enddate = $(enddate);
    if(r.sponsored.dateFromInput(startdate) >= r.sponsored.dateFromInput(enddate)) {
      var newd = new Date();
      newd.setTime(startdate.datepicker('getDate').getTime() + 86400*1000);
      enddate.val((newd.getMonth()+1) + "/" +
        newd.getDate() + "/" + newd.getFullYear());
    }
    $("#datepicker-" + enddate.attr("id")).datepicker("destroy");
  },

  targeting_on: function(elem) {
      $(elem).parents(".campaign").find(".targeting")
          .find('*[name="sr"]').prop("disabled", "").end().slideDown();
  },

  targeting_off: function(elem) {
      $(elem).parents(".campaign").find(".targeting")
          .find('*[name="sr"]').prop("disabled", "disabled").end().slideUp();
  },

  detach_campaign_form: function() {
    console.log('detaching')
      /* remove datepicker from fields */
      $("#campaign").find(".datepicker").each(function() {
              $(this).datepicker("destroy").siblings().unbind();
          });

      /* detach and return */
      var campaign = $("#campaign").detach();
      return campaign;
  },

  cancel_edit: function(callback) {
      if($("#campaign").parents('tr:first').length) {
          var tr = $("#campaign").parents("tr:first").prev();
          /* copy the campaign element */
          /* delete the original */
          $("#campaign").fadeOut(function() {
                  $(this).parent('tr').prev().fadeIn();
                  var td = $(this).parent();
                  var campaign = r.sponsored.detach_campaign_form();
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
  },

  del_campaign: function(elem) {
      var campaign_id36 = $(elem).find('*[name="campaign_id36"]').val();
      var link_id = $("#campaign").find('*[name="link_id"]').val();
      $.request("delete_campaign", {"campaign_id36": campaign_id36,
                                    "link_id": link_id},
                null, true, "json", false);
      $(elem).children(":first").delete_table_row(r.sponsored.check_number_of_campaigns);
  },

  edit_campaign: function(elem) {
      /* find the table row in question */
      var tr = $(elem).get(0);

      if ($("#campaign").parents('tr:first').get(0) != tr) {

          r.sponsored.cancel_edit(function() {

              /* copy the campaign element */
              var campaign = r.sponsored.detach_campaign_form();

              $(".existing-campaigns table")
                  .insert_table_rows([{"id": "edit-campaign-tr",
                                  "css_class": "", "cells": [""]}], 
                      tr.rowIndex + 1);
              $("#edit-campaign-tr").children('td:first')
                  .attr("colspan", 8).append(campaign).end()
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
                          r.sponsored.fill_inputs();
                          r.sponsored.check_bid();
                          c.fadeIn();
                      } );
              }
              );
      }
  },

  check_number_of_campaigns: function(){
      if ($(".campaign-row").length >= $(".existing-campaigns").data("max-campaigns")){
        $(".error.TOO_MANY_CAMPAIGNS").fadeIn();
        $("button.new-campaign").attr("disabled", "disabled");
        return true;
      } else {
        $(".error.TOO_MANY_CAMPAIGNS").fadeOut();
        $("button.new-campaign").removeAttr("disabled");
        return false;
      }
  },

  create_campaign: function() {
      if (r.sponsored.check_number_of_campaigns()){
          return;
      }
      r.sponsored.cancel_edit(function() {;
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
              r.sponsored.fill_inputs();
          });
  },

  free_campaign: function(elem) {
      var campaign_id36 = $(elem).find('*[name="campaign_id36"]').val();
      var link_id = $("#campaign").find('*[name="link_id"]').val();
      $.request("freebie", {"campaign_id36": campaign_id36, "link_id": link_id},
                null, true, "json", false);
      $(elem).find(".free").fadeOut();
      return false; 
  },

  pay_campaign: function(elem) {
      $.redirect($(elem).find('input[name="pay_url"]').val());
  },

  view_campaign: function(elem) {
      $.redirect($(elem).find('input[name="view_live_url"]').val());
  }
};

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
                          bid, spent, cpm, speed, targeting, flags) {
    r.sponsored.cancel_edit(function() {
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
      var row = [start_date, end_date, duration, "$" + bid, "$" + spent, speed, targeting, data];
      $(".existing-campaigns .error").hide();
      var css_class = get_flag_class(flags);
      $(".existing-campaigns table").show()
      .insert_table_rows([{"id": "", "css_class": css_class, 
                           "cells": row}], -1);
      r.sponsored.check_number_of_campaigns();
      $.set_up_campaigns()
        });
   return $;
};

$.update_campaign = function(campaign_id36, start_date, end_date,
                             duration, bid, spent, cpm, speed, targeting, flags) {
    r.sponsored.cancel_edit(function() {
            $('.existing-campaigns input[name="campaign_id36"]')
                .filter('*[value="' + (campaign_id36 || '0') + '"]')
                .parents("tr").removeClass()
            .addClass(get_flag_class(flags))
                .children(":first").html(start_date)
                .next().html(end_date)
                .next().html(duration)
                .next().html("$" + bid).removeClass()
                .next().html("$" + spent)
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
                            .click(function() { r.sponsored.view_campaign(tr) }));
                }
                /* once paid, we shouldn't muck around with the campaign */
                if(!tr.hasClass("complete")) {
                    if (tr.hasClass("sponsor") && !tr.hasClass("free")) {
                        $(bid_td).append($(free).addClass("free")
                                     .click(function() { r.sponsored.free_campaign(tr) }))
                    }
                    else if (!tr.hasClass("paid")) {
                        $(bid_td).prepend($(pay).addClass("pay fancybutton")
                                     .click(function() { r.sponsored.pay_campaign(tr) }));
                    } else if (tr.hasClass("free")) {
                        $(bid_td).addClass("free paid")
                            .prepend("<span class='info'>freebie</span>");
                    } else {
                        (bid_td).addClass("paid")
                            .prepend($(repay).addClass("pay fancybutton")
                                     .click(function() { r.sponsored.pay_campaign(tr) }));
                    }
                    var e = $(edit).addClass("edit fancybutton")
                        .click(function() { r.sponsored.edit_campaign(tr); });
                    var d = $(del).addClass("d fancybutton")
                        .click(function() { r.sponsored.del_campaign(tr); });
                    $(td).append(e).append(d);
                }
                else {
                    if (!tr.hasClass("live")) {
                      $(td).append("<span class='info'>complete</span>");
                    }
                    $(bid_td).addClass("paid")
                    /* sponsors can always edit */
                    if (tr.hasClass("sponsor")) {
                        var e = $(edit).addClass("edit fancybutton")
                            .click(function() { r.sponsored.edit_campaign(tr); });
                        $(td).append(e);
                    }
                }
            }
        });
    return $;

}

}(jQuery));
