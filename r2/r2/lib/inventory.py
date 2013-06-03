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
from datetime import datetime, timedelta
import re

from pylons import g
from sqlalchemy import func

from r2.lib.memoize import memoize
from r2.lib.utils import to_date
from r2.models import (
    PromoCampaign,
    PromotionWeights,
    NO_TRANSACTION,
    traffic,
)
from r2.models.promo_metrics import PromoMetrics
from r2.models.subreddit import DefaultSR, Subreddit

NDAYS_TO_QUERY = 14  # how much history to use in the estimate
MIN_DAILY_CASS_KEY = 'min_daily_pageviews.GET_listing'
PAGEVIEWS_REGEXP = re.compile('(.*)-GET_listing')

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
        date = start + timedelta(i)
        predicted[date] = min_daily
    return predicted


def update_prediction_data():
    """Fetch prediction data and write it to cassandra."""
    min_daily_by_sr = _min_daily_pageviews_by_sr(NDAYS_TO_QUERY)
    PromoMetrics.set(MIN_DAILY_CASS_KEY, min_daily_by_sr)


def _min_daily_pageviews_by_sr(ndays=NDAYS_TO_QUERY, end_date=None):
    """Return dict mapping sr_name to min_pageviews over the last ndays."""
    if not end_date:
        end_date = datetime.now()
    stop = end_date.date()
    start = stop - timedelta(ndays)
    cls = traffic.PageviewsBySubredditAndPath
    q = (traffic.Session.query(cls.srpath, func.min(cls.pageview_count))
                               .filter(cls.interval == 'day')
                               .filter(cls.date >= start)
                               .filter(cls.date < stop)
                               .filter(cls.srpath.like('%-GET_listing'))
                               .group_by(cls.srpath))

    # row looks like: ('lightpainting-GET_listing', 16)
    retval = {}
    for row in q:
        m = PAGEVIEWS_REGEXP.match(row[0])
        if m:
            retval[m.group(1)] = row[1]
    return retval


@memoize('min_daily_pageviews', time=60*60)
def min_daily_pageviews(sr, ndays=NDAYS_TO_QUERY):
    return 10000
    last_modified = traffic.get_traffic_last_modified()
    query_end = last_modified - datetime.timedelta(days=1)
    query_end = query_end.replace(hour=0, minute=0, second=0, microsecond=0)
    query_start = query_end - datetime.timedelta(days=ndays)

    time_points = traffic.get_time_points('day', query_start, query_end)
    cls = traffic.PageviewsBySubredditAndPath
    q = (traffic.Session.query(cls.srpath, func.min(cls.pageview_count))
                               .filter(cls.interval == 'day')
                               .filter(cls.date.in_(time_points))
                               .filter(cls.srpath == '%s-GET_listing' % sr.name)
                               .group_by(cls.srpath))
    r = list(q)
    if not r:
        raise ValueError('No traffic for %s' % sr.name)
    elif len(r) != 1:
        raise ValueError('Got weird traffic result for %s: %s' % (sr.name, r))
    else:
        return r[0][1]


def get_date_range(start, end):
    start, end = filter(to_date, [start, end])
    dates = [start + timedelta(i) for i in xrange((end - start).days)]
    return dates

def get_sold_pageviews(sr, start, end):
    sr_name = '' if isinstance(sr, DefaultSR) else sr.name
    dates = set(get_date_range(start, end))

    q = (PromotionWeights.query()
                .filter(PromotionWeights.sr_name == sr_name)
                .filter(PromotionWeights.date.in_(dates)))
    promo_weights = list(q)
    campaigns = PromoCampaign._byID([pw.promo_idx for pw in promo_weights],
                                    data=True, return_dict=False)

    r = dict.fromkeys(dates, 0)
    for camp in campaigns:
        if camp.trans_id == NO_TRANSACTION:
            continue
        ndays = (camp.end_date - camp.start_date).days
        daily_impressions = camp.impressions / ndays
        camp_dates = set(get_date_range(camp.start_date, camp.end_date))
        for date in camp_dates.intersection(dates):
            r[date] += daily_impressions
    return r


def get_available_pageviews(sr, start, end):
    daily_available = min_daily_pageviews(sr)
    sold_by_date = get_sold_pageviews(sr, start, end)
    return {date: max(0, daily_available - sold)
            for date, sold in sold_by_date.iteritems()}


def get_available_pageviews_json(sr, start, end):
    available_pageviews = get_available_pageviews(sr, start, end)
    return {d.strftime('%m/%d/%Y'): val
            for (d, val) in available_pageviews.iteritems()}


def get_oversold(sr, start, end, daily_request):
    available_by_date = get_available_pageviews(sr, start, end)
    oversold = {}
    for date, available in available_by_date.iteritems():
        if available < daily_request:
            oversold[date] = available
    return oversold
