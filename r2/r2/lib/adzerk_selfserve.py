from collections import defaultdict
import datetime
import json

import adzerk

from pylons import g

from r2.lib import authorize, promote
from r2.lib.db.thing import NotFound
from r2.lib.filters import spaceCompress
from r2.models import Account, Link, PromoCampaign

# Move to ini
adzerk_site_id = 27843
adzerk_advertiser_id = 20329    # self serve
adzerk_priority_id = 21520
adzerk_channel_id = 8186    # All sites
adzerk_publisher_id = 9649
adzerk_network_id = 5292


"""
Adzerk Hierarchy
* a Campaign is a container for a related set of ads
  * each Campaign consists of one or more Flights
* a Flight is a set of rules for the ad should be served
  * rules can be impression goals, tracking methods, dates, targeting
  * each Flight contains one or more Creatives
* a Creative is the actual ad html or image
* a Creative Flight Map is an object that connects a Creative to a Flight
  * a Creative can be associated with multiple Flights
  * each Flight can contain multiple Creatives

Mapping from reddit objects
* reddit (promoted) Link - adzerk Campaign, adzerk Creative
* reddit PromoCampaign - adzerk Flight
"""


def date_to_adzerk(d):
    return d.strftime('%m/%d/%Y')


def srname_to_keyword(srname):
    return srname or 'reddit.com'


def render_link(link, campaign):
    author = Account._byID(link.author_id, data=True)
    return json.dumps({
        'link': link._fullname,
        'campaign': campaign._fullname,
        'title': link.title,
        'author': author.name,
        'target': campaign.sr_name,
    })


class Adzerk(object):
    """Wrapper over adzerk state to get closer to reddit's ad model"""
    def __init__(self, key):
        adzerk.set_key(key)
        self.sites = []
        self.zones = []
        self.channels = []
        self.publishers = []
        self.priorities = []
        self.advertisers = []
        self.creatives = []
        self.flights = []
        self.campaigns = []
        self.cfmaps = []
        self.flights_by_campaign = defaultdict(list)
        self.cfmaps_by_flight = defaultdict(list)
        self._loaded = False

    def load(self):
        """Load entire state of adzerk"""
        self.sites = adzerk.Site.list()
        self.zones = adzerk.Zone.list()
        self.channels = adzerk.Channel.list()
        self.publishers = adzerk.Publisher.list()
        self.priorities = adzerk.Priority.list()
        self.advertisers = adzerk.Advertiser.list()
        for advertiser in self.advertisers:
            creatives = adzerk.Creative.list(advertiser.Id) or []
            self.creatives.extend(creatives)
        self.flights = adzerk.Flight.list()
        self.campaigns = adzerk.Campaign.list()
        for flight in self.flights:
            cfmaps = adzerk.CreativeFlightMap.list(flight.Id) or []
            self.cfmaps.extend(cfmaps)

        for flight in self.flights:
            self.flights_by_campaign[flight.CampaignId].append(flight)

        for cfmap in self.cfmaps:
            self.cfmaps_by_flight[cfmap.FlightId].append(cfmap)

        self.campaigns_by_name = {campaign.Name: campaign
                                  for campaign in self.campaigns}
        self.creatives_by_title = {creative.Title: creative
                                   for creative in self.creatives}
        self.flights_by_name = {flight.Name: flight for flight in self.flights}

        self.cfmap_lookup = {}
        for cfmap in self.cfmaps:
            name = (cfmap.FlightId, cfmap.Creative.Id)
            self.cfmap_lookup[name] = cfmap
        self._loaded = True

    def add_thing_attributes(self):
        """Add adzerk Ids to reddit links and campaigns"""
        if not self._loaded:
            self.load()

        for az_campaign in self.campaigns:
            try:
                link = Link._by_fullname(az_campaign.Name, data=True)
            except:
                print 'skipping %s' % az_campaign.Name
                continue

            print '%s is %s' % (link, az_campaign)
            if hasattr(link, 'adzerk_campaign_id'):
                print 'existing %s - correct %s' % (link.adzerk_campaign_id,
                                                    az_campaign.Id)
            else:
                print 'setting adzerk_campaign_id to %s' % az_campaign.Id
                link.adzerk_campaign_id = az_campaign.Id
                link._commit()

        for az_creative in self.creatives:
            try:
                link_name, campaign_name = az_creative.Title.split('-')
                campaign = PromoCampaign._by_fullname(campaign_name, data=True)
            except:
                print 'skipping %s' % az_creative.Title
                continue

            print '%s is %s' % (campaign, az_creative)
            if hasattr(campaign, 'adzerk_creative_id'):
                print 'existing %s - correct %s' % (campaign.adzerk_creative_id,
                                                    az_creative.Id)
            else:
                print 'setting adzerk_creative_id to %s' % az_creative.Id
                campaign.adzerk_creative_id = az_creative.Id
                campaign._commit()

        for az_flight in self.flights:
            try:
                campaign = PromoCampaign._by_fullname(az_flight.Name, data=True)
            except:
                print 'skipping %s' % az_flight.Name
                continue

            print '%s is %s' % (campaign, az_flight)
            if hasattr(campaign, 'adzerk_flight_id'):
                print 'existing %s - correct %s' % (campaign.adzerk_flight_id,
                                                    az_flight.Id)
            else:
                print 'setting adzerk_flight_id to %s' % az_flight.Id
                campaign.adzerk_flight_id = az_flight.Id
                campaign._commit()

        az_flights_by_id = {az_flight.Id: az_flight
                            for az_flight in self.flights}

        for az_cfmap in self.cfmaps:
            az_flight = az_flights_by_id[az_cfmap.FlightId]
            try:
                campaign = PromoCampaign._by_fullname(az_flight.Name, data=True)
            except:
                print 'skipping %s' % az_flight.Name
                continue

            print '%s is %s' % (campaign, az_cfmap)
            if hasattr(campaign, 'adzerk_cfmap_id'):
                print 'existing %s - correct %s' % (campaign.adzerk_cfmap_id,
                                                    az_cfmap.Id)
            else:
                print 'setting adzerk_cfmap_id to %s' % az_cfmap.Id
                campaign.adzerk_cfmap_id = az_cfmap.Id
                campaign._commit()

    def update_campaign(self, link):
        """Add/update a reddit link as an Adzerk Campaign"""
        if hasattr(link, 'adzerk_campaign_id'):
            az_campaign = adzerk.Campaign.get(link.adzerk_campaign_id)
        else:
            az_campaign = None

        d = {
            'AdvertiserId': adzerk_advertiser_id,
            'IsDeleted': False,
            'IsActive': True,
            'Price': 0,
        }

        if az_campaign:
            print 'updating adzerk campaign for %s' % link._fullname
            for key, val in d.iteritems():
                setattr(az_campaign, key, val)
            az_campaign._send()
        else:
            print 'creating adzerk campaign for %s' % link._fullname
            d.update({
                'Name': link._fullname,
                'Flights': [],
                'StartDate': date_to_adzerk(datetime.datetime.now(g.tz)),
            })
            az_campaign = adzerk.Campaign.create(**d)
            link.adzerk_campaign_id = az_campaign.Id
            link._commit()
        return az_campaign

    def update_creative(self, link, campaign):
        """Add/update a reddit link/campaign as an Adzerk Creative"""
        if hasattr(campaign, 'adzerk_creative_id'):
            az_creative = adzerk.Creative.get(campaign.adzerk_creative_id)
        else:
            az_creative = None

        title = '-'.join((link._fullname, campaign._fullname))
        d = {
            'Body': title,
            'ScriptBody': render_link(link, campaign),
            'AdvertiserId': adzerk_advertiser_id,
            'AdTypeId': 4, # leaderboard
            'Alt': link.title,
            'Url': link.url,
            'IsHTMLJS': True,
            'IsSync': False,
            'IsDeleted': False,
            'IsActive': True,
        }

        if az_creative:
            print 'updating adzerk creative for %s %s' % (link._fullname,
                                                          campaign._fullname)
            for key, val in d.iteritems():
                setattr(az_creative, key, val)
            az_creative._send()
        else:
            print 'creating adzerk creative for %s %s' % (link._fullname,
                                                          campaign._fullname)
            d.update({'Title': title})
            az_creative = adzerk.Creative.create(**d)
            campaign.adzerk_creative_id = az_creative.Id
            campaign._commit()
        return az_creative

    def update_flight(self, link, campaign):
        """Add/update a reddit campaign as an Adzerk Flight"""
        if hasattr(campaign, 'adzerk_flight_id'):
            az_flight = adzerk.Flight.get(campaign.adzerk_flight_id)
        else:
            az_flight = None

        az_campaign = adzerk.Campaign.get(link.adzerk_campaign_id)

        d = {
            'StartDate': date_to_adzerk(campaign.start_date),
            'EndDate': date_to_adzerk(campaign.end_date),
            'Price': campaign.cpm,
            'OptionType': 1, # 1: CPM, 2: Remainder
            'Impressions': campaign.impressions,
            'IsUnlimited': False,
            'IsFullSpeed': not campaign.serve_even,
            'Keywords': srname_to_keyword(campaign.sr_name),
            'CampaignId': az_campaign.Id,
            'PriorityId': adzerk_priority_id,
            'IsDeleted': False,
            'IsActive': True,
            'GoalType': 1, # 1: Impressions
            'RateType': 2, # 2: CPM
            'IsFreqCap': False,
        }

        if az_flight:
            print 'updating adzerk flight for %s' % campaign._fullname
            for key, val in d.iteritems():
                setattr(az_flight, key, val)
            az_flight._send()
        else:
            print 'creating adzerk flight for %s' % campaign._fullname
            d.update({'Name': campaign._fullname})
            az_flight = adzerk.Flight.create(**d)
            campaign.adzerk_flight_id = az_flight.Id
            campaign._commit()
        return az_flight

    def update_cfmap(self, link, campaign):
        """Add/update a CreativeFlightMap.
        
        Map the the reddit link (adzerk Creative) and reddit campaign (adzerk
        Flight).

        """

        az_campaign = adzerk.Campaign.get(link.adzerk_campaign_id)
        az_creative = adzerk.Creative.get(campaign.adzerk_creative_id)
        az_flight = adzerk.Flight.get(campaign.adzerk_flight_id)

        if hasattr(campaign, 'adzerk_cfmap_id'):
            az_cfmap = adzerk.CreativeFlightMap.get(az_flight.Id,
                                                    campaign.adzerk_cfmap_id)
        else:
            az_cfmap = None

        d = {
            'SizeOverride': False,
            'CampaignId': az_campaign.Id,
            'PublisherAccountId': adzerk_advertiser_id,
            'Percentage': 100,  # Each flight only has one creative (what about autobalanced)
            'DistributionType': 2, # 2: Percentage, 1: Auto-Balanced, 0: ???
            'Iframe': False,
            'Creative': {'Id': az_creative.Id},
            'FlightId': az_flight.Id,
            'Impressions': campaign.impressions,
            'IsDeleted': False,
            'IsActive': True,
        }

        if az_cfmap:
            print 'updating adzerk cfmap for %s %s' % (link._fullname,
                                                       campaign._fullname)
            for key, val in d.iteritems():
                setattr(az_cfmap, key, val)
            az_cfmap._send()
        else:
            print 'creating adzerk cfmap for %s %s' % (link._fullname,
                                                       campaign._fullname)
            az_cfmap = adzerk.CreativeFlightMap.create(az_flight.Id, **d)
            campaign.adzerk_cfmap_id = az_cfmap.Id
            campaign._commit()
        return az_cfmap

    def update_adzerk(self, link, campaign):
        az_campaign = self.update_campaign(link)
        az_creative = self.update_creative(link, campaign)
        az_flight = self.update_flight(link, campaign)
        az_cfmap = self.update_cfmap(link, campaign)


def update_adzerk(offset=0):
    # make sure is_charged_transaction and is_accepted are the only criteria
    # for a campaign going live!
    adzerk_state = Adzerk(g.adzerk_key)

    for link, campaign, weight in promote.accepted_campaigns(offset=offset):
        if (authorize.is_charged_transaction(campaign.trans_id, campaign._id) and
            promote.is_accepted(link)):
            adzerk_state.update_adzerk(link, campaign)


def deactivate_link(link):
    # Can't deactivate creative without the campaign, should be ok
    adzerk = Adzerk(g.adzerk_key)
    adzerk.load()

    az_campaign = adzerk.link_to_campaign(link)
    az_campaign.IsActive = False
    az_campaign._send()


def deactivate_campaign(link, campaign):
    # Do we need to deactivate the link objects and map?
    # hook into promote.void_campaign, promote.delete_campaign. What about
    # promote.reject_promotion
    adzerk = Adzerk(g.adzerk_key)
    adzerk.load()

    az_flight = adzerk.campaign_to_flight(campaign)
    az_flight.IsActive = False
    az_flight._send()

"""
authorize/bidding communicates with a remote service and backs it with a db,
we could do something similar for adzerk. Talk to keith about this at 1:00

r2.lib.promote.Run() run hourly to update promos
* charge_pending(offset=offset + 1)
* charge_pending(offset=offset)
* amqp.add_item(UPDATE_QUEUE, json.dumps(QUEUE_ALL),
                delivery_mode=amqp.DELIVERY_TRANSIENT)
  amqp.worker.join()

charge_pending:
* iterates over promote.accepted_campaigns, which grabs the list of
  PromotionWeights from the day and checks that the links are accepted
* for each accepted campaign check if it's been charge if not try to charge
* when are campaigns auth'ed?

UPDATE_QUEUE is update_promos_q
QUEUE_ALL is 'all', and signals to run make_daily_promotions, which is also
executed whenever a promotion is changed

make_daily_promotions:
* iterate over promote.get_scheduled which is like accepted_campaigns but only
  yields items that have been charged
  * set links to over_18 if they advertise in an over_18 subreddit
* eventually calls promote.set_live_promotions()

set_live_promotions:
* updates LiveAdWeights

do I need to redo the whole flow? Maybe because charging/billing will happen
after delivery! try to map it out!

* get a list of things that should be going live
* auth them
* update adzerk
* get list of things that were live
* charge them? (every day?)

Can we switch to using stripe and make sure there's a valid customer for the
user and then charge once a day? Fees are 2.9% + $0.30

Mock out both with Stripe and with Authorize.net
* auth created by POST_update_pay
* charge created by charge_pending (really an auth capture)
* by default the capture will be for the full amount, optionally can send a
  different amount. Would we wait until the campaign was finished?


* auth/void to validate payment in POST_update_pay
    * this might be a separate thing, auths are only good for 30 days! we're
      being reckless by not checking that
* charge in full before campaign goes live
* after campaign is complete (need to detect this!) send a refund
    * start with this part


"""


""""TESTING:
make a link and campaign
edit the campign so it's live with promote.edit_campaign
make it free with promote.free_campaign
"auth" it with promote.charge_pending
make it live with promote.make_daily_promotions
send it to adzerk with adzerk.update_adzerk(link, camp)

why is my creative not active? the slider is set to off
same happens to other creatives on my link when I update the link (campaign)
* link_to_campaign is safe
* link_to_creative is safe
* campaign_to_flight is safe
* make_cfmap is the culprit!

will it get set to active if I re-run update_adzerk?

see if I can separate stuff into a plugin. Seems reasonable!

When does charge pending run? day in advance? If so that should also update
adzerk probably. it can take up to 30 minutes for a campaign to go active

do we want to increase the # of impressions reported to adzerk?

do we need to pull down full adzerk state each time?

do we need to /do we limit to site_id for campaigns/flights/creatives?
* we don't but maybe we should? might not be needed due to keyword targeting?
  just make sure to disable any of my test ads
 
should updates also update local representation of adzerk state if it's loaded
"""