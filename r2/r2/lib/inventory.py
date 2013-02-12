# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2013 reddit
# Inc. All Rights Reserved.
###############################################################################


from collections import OrderedDict
import datetime
import math
import re

from pylons import g
from sqlalchemy import func

from r2.lib.utils import to_date
from r2.models import traffic
from r2.models.promo_metrics import PromoMetrics
from r2.models.subreddit import DefaultSR
from r2.models.bidding import PromotionWeights
from r2.models.promo import PromoCampaign, NO_TRANSACTION


NDAYS_TO_QUERY = 14  # how much history to use in the estimate
MIN_DAILY_CASS_KEY = 'min_daily_pageviews.GET_listing'
PAGEVIEWS_REGEXP = re.compile('(.*)-GET_listing')


def impressions_from_bid(bid):
    impressions = bid / (g.CPM_PENNIES / 100.) * 1000
    return int(impressions)


# Precomputing
def get_predicted_by_date(sr_name, start, stop=None):
    """Return dict mapping datetime objects to predicted pageviews."""
    if not sr_name:
        sr_name = DefaultSR.name.lower()
    # lowest pageviews any day the last 2 weeks
    min_daily = PromoMetrics.get(MIN_DAILY_CASS_KEY, sr_name).get(sr_name, 0)
    # expand out to the requested range of dates
    ndays = (stop - start).days if stop else 1  # default is one day
    predicted = OrderedDict()
    for i in range(ndays):
        date = start + datetime.timedelta(i)
        predicted[date] = min_daily
    return predicted


def update_prediction_data():
    """Fetch prediction data and write it to cassandra."""
    min_daily_by_sr = all_min_daily_pageviews(NDAYS_TO_QUERY)
    PromoMetrics.set(MIN_DAILY_CASS_KEY, min_daily_by_sr)

def all_min_daily_pageviews(ndays=NDAYS_TO_QUERY, end_date=None):
    if not end_date:
        end_date = datetime.datetime.now() - datetime.timedelta(days=1)   # notice that we can't use g.tz

    end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - datetime.timedelta(days=ndays)
    time_points = traffic.get_time_points('day', start_date, end_date)
    cls = traffic.PageviewsBySubredditAndPath

    q = (traffic.Session.query(cls.srpath, func.min(cls.pageview_count))
                               .filter(cls.interval == 'day')
                               .filter(cls.date.in_(time_points))
                               .filter(cls.srpath.like('%-GET_listing'))
                               .group_by(cls.srpath))

    retval = {}
    for row in q:
        m = PAGEVIEWS_REGEXP.match(row[0])
        if m:
            retval[m.group(1)] = row[1]
    return retval

# Direct querying
def get_scheduled_pageviews(sr_name, dates):
    # PromotionWeights uses sr_name '' to indicate front page
    if sr_name == DefaultSR.name.lower():
        sr_name = ''

    q = (PromotionWeights.query()
                .filter(PromotionWeights.sr_name == sr_name)
                .filter(PromotionWeights.date.in_(dates)))
    promo_weights = list(q)
    campaigns = PromoCampaign._byID([pw.promo_idx for pw in promo_weights],
                                    data=True, return_dict=True)

    r = dict.fromkeys(dates, 0)
    for pw in promo_weights:
        paid = campaigns[pw.promo_idx].trans_id != NO_TRANSACTION
        if not paid:
            continue

        bid = pw.bid
        pageviews = impressions_from_bid(bid)
        r[pw.date] += pageviews
    return r


def get_predicted_pageviews(sr_name, dates):
    """Make a conservative estimate of future pageviews

    In the future can base this off running average and day of the week. For
    now just return the minimum pageviews from last 14 days.

    """

    min_pageviews = min_daily_pageviews_by_sr(sr_name, ndays=14)
    return dict.fromkeys(dates, min_pageviews)


def min_daily_pageviews_by_sr(sr_name, ndays=NDAYS_TO_QUERY):
    """Return minimum pageviews for sr over the last ndays."""

    return 10000


# Interfaces
def fuzz_impressions(imps, multiple=500):
    """Return imps rounded down to nearest multiple."""
    if imps > 0:
        return int(multiple * math.floor(float(imps) / multiple))
    else:
        return 0


def get_available_impressions(sr_name, start_date, end_date, fuzzed=False):
    start_date, end_date = to_date(start_date), to_date(end_date)
    dates = [start_date + datetime.timedelta(i)
             for i in xrange((end_date - start_date).days)]

    scheduled = get_scheduled_pageviews(sr_name, dates)
    total = get_predicted_pageviews(sr_name, dates)
    available = {}
    for d in dates:
        if fuzzed:
            available[d] = fuzz_impressions(total[d] - scheduled[d])
        else:
            available[d] = total[d] - scheduled[d]
    return available


def get_oversold_dates(sr_name, bid, start_date, end_date):
    start_date, end_date = to_date(start_date), to_date(end_date)
    duration = max((end_date - start_date).days, 1)
    requested_per_day = impressions_from_bid(bid / duration)
    available = get_available_impressions(sr_name, start_date, end_date)
    oversold = [d for d, avail in available.items()
                if avail < requested_per_day]
    return oversold
