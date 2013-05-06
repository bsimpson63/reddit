from collections import defaultdict
import datetime
import json

import adzerk

from pylons import c, g

from r2.lib.filters import spaceCompress
from r2.lib.utils import to36
from r2.models import Account, Link

# Move to ini
adzerk_site_id = 27843
adzerk_advertiser_id = 20329    # self serve
adzerk_priority_id = 21520
adzerk_channel_id = 8186    # All sites
adzerk_publisher_id = 9649
adzerk_network_id = 5292

"""
Required pieces:
- Link --> adzerk Campaign
- Link --> adzerk Creative
  - update at intervals to reflect #comments, votes?
- PromoCampaign --> adzerk Flight
- Link, PromoCampaign --> adzerk FlightCampaignMap
- void

- adzerk status
  - Campaigns, Creatives, Flights, Maps

- reddit status
  - PromotionWeights --> adzerk

"""

# in adzerk's world, creatives aren't limited to a single campaign
# or flight
# in reddit's world Links are Creative and Campaign
# and a PromoCampaigns are Flights
# a Link can have multiple PromoCampaigns
# need to make sure that each Flights are tied to their Creative
# maps have some delivery options, need to check how to use those!

# keyword for frontpage is reddit.com

"""
From Adzerk Hierarchy
* a campaign is a container for a related set of ads
  * each campaign consists of one or more flights
* a flight is a set of rules for the ad should be served
  * rules can be impression goals, tracking methods, dates, targeting
  * each flight has a priority
  * each flight contains one or more creatives
* a creative is the actual ad html or whatever
* what about creative flight map, whose settings are those?
  * aren't on the creative because the creative could be used by multiple
    flights/campaigns
  * aren't on the flight because a flight could contain multiple creatives!
  * so: not redundant, necessary organizational piece

Campaign contains several flights
Flight contains several creatives
a creative could be assigned to several different flights though


To fully describe a Campaign:
* which flights does it contain
* (do we need to know creatives?)

To fully describe a Flight
* which creatives does it contain
"""

"""
Requirements:
* get state of adzerk
* update adzerk with given list of links, campaigns
  * don't make duplicates! update if existing
    * set attributes on reddit things, also we will be naming the adzerk things
      with the reddit fullname
* on highest level should not need manal checking, just pass a link, campaign
  and update adzerk if needed
* overall check to make sure there aren't extra things active that shouldn't be

Do we need to not set Id if it doesn't exist?

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

    def load(self):
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

    def link_to_campaign(self, link):
        """Add/update a reddit link as an Adzerk Campaign"""
        campaign = self.campaigns_by_name.get(link._fullname)
        d = {
            'AdvertiserId': adzerk_advertiser_id,
            'IsDeleted': False,
            'IsActive': True,
            'Price': 0,
        }

        if campaign:
            print 'updating adzerk campaign for %s' % link._fullname
            for key, val in d.iteritems():
                setattr(campaign, key, val)
            campaign._send()
        else:
            print 'creating adzerk campaign for %s' % link._fullname
            d.update({
                'Name': link._fullname,
                'Flights': [],  # TODO: do we want to overwrite this in existing?
                'StartDate': date_to_adzerk(datetime.datetime.now(g.tz)),
            })
            campaign = adzerk.Campaign.create(**d)
            self.campaigns.append(campaign)
            self.campaigns_by_name[link._fullname] = campaign
        return campaign

    def link_to_creative(self, link, campaign):
        """Add/update a reddit link as an Adzerk Creative"""
        title = '-'.join((link._fullname, campaign._fullname))
        creative = self.creatives_by_title.get(title)
        d = {
            'Body': title,
            'ScriptBody': render_link(link, campaign),
            'AdvertiserId': adzerk_advertiser_id,
            'AdTypeId': 4, # leaderboard
            'Alt': link.title,
            'IsHTMLJS': True,
            'IsSync': False,
            'IsDeleted': False,
            'IsActive': True,
        }

        if creative:
            print 'updating adzerk creative for %s %s' % (link._fullname,
                                                          campaign._fullname)
            for key, val in d.iteritems():
                setattr(creative, key, val)
            creative._send()
        else:
            print 'creating adzerk creative for %s %s' % (link._fullname,
                                                          campaign._fullname)
            d.update({'Title': title})
            creative = adzerk.Creative.create(**d)
            self.creatives.append(creative)
            self.creatives_by_title[title] = creative
        return creative

    def campaign_to_flight(self, campaign):
        """Add/update a reddit campaign as an Adzerk Flight"""
        az_campaign_name = Link._fullname_from_id36(to36(campaign.link_id))
        try:
            az_campaign = self.campaigns_by_name[az_campaign_name]
        except KeyError:
            raise ValueError('missing campaign for flight')

        flight = self.flights_by_name.get(campaign._fullname)
        d = {
            'StartDate': date_to_adzerk(campaign.start_date),
            'EndDate': date_to_adzerk(campaign.end_date),
            'Price': 1, # TODO
            'OptionType': 1, # 1: CPM, 2: Remainder
            'Impressions': getattr(campaign, 'impressions', 1000), # TODO: handle this
            'IsUnlimited': False,
            'IsFullSpeed': False,
            'Keywords': srname_to_keyword(campaign.sr_name),
            'CampaignId': az_campaign.Id,
            'PriorityId': adzerk_priority_id,
            'IsDeleted': False,
            'IsActive': True,
            'GoalType': 1, # 1: Impressions
            'RateType': 2, # 2: CPM
            'IsFreqCap': True,  # TODO: think about options for freq cap
            'FreqCap': getattr(campaign, 'maxdaily', 1000), # TODO: handle this
            'FreqCapDuration': 1,
            'FreqCapType': 2, # day
        }

        if flight:
            print 'updating adzerk flight for %s' % campaign._fullname
            for key, val in d.iteritems():
                setattr(flight, key, val)
            flight._send()
        else:
            print 'creating adzerk flight for %s' % campaign._fullname
            d.update({'Name': campaign._fullname})
            flight = adzerk.Flight.create(**d)
            self.flights.append(flight)
            self.flights_by_name[campaign._fullname] = flight
            self.flights_by_campaign[flight.CampaignId].append(flight)
        return flight

    def make_cfmap(self, link, campaign):
        """Make a CreativeFlightMap.
        
        Map the the reddit link (adzerk Creative) and reddit campaign (adzerk
        Flight).

        """

        az_campaign = self.campaigns_by_name[link._fullname]
        creative_title = '-'.join((link._fullname, campaign._fullname))
        az_creative = self.creatives_by_title[creative_title]
        az_flight = self.flights_by_name[campaign._fullname]

        cfmap = self.cfmap_lookup.get((az_flight.Id, az_creative.Id))
        d = {
            'SizeOverride': False,
            'CampaignId': az_campaign.Id,
            'PublisherAccountId': adzerk_advertiser_id,
            'Percentage': 100,  # Each flight only has one creative (what about autobalanced)
            'DistributionType': 2, # 2: Percentage, 1: Auto-Balanced, 0: ???
            'Iframe': False,
            'Creative': {'Id': az_creative.Id},
            'FlightId': az_flight.Id,
            'Impressions': getattr(campaign, 'impressions', 1000), # TODO: handle this
            'IsDeleted': False,
            'IsActive': True,
        }

        if cfmap:
            print 'updating adzerk cfmap for %s %s' % (link._fullname,
                                                       campaign._fullname)
            for key, val in d.iteritems():
                setattr(cfmap, key, val)
            cfmap._send()
        else:
            print 'creating adzerk cfmap for %s %s' % (link._fullname,
                                                       campaign._fullname)
            cfmap = adzerk.CreativeFlightMap.create(az_flight.Id, **d)
            self.cfmaps.append(cfmap)
            self.cfmaps_by_flight[az_flight.Id].append(cfmap)
            self.cfmap_lookup[(az_flight.Id, az_creative.Id)] = cfmap
        return cfmap

    def update_adzerk(self, link, campaign):
        # Could throw adzerk.AdzerkError
        az_campaign = self.link_to_campaign(link)
        az_creative = self.link_to_creative(link, campaign)
        az_flight = self.campaign_to_flight(campaign)
        az_cfmap = self.make_cfmap(link, campaign)

    def mirror(self, link_campaign_tuples):
        """Update adzerk to activate only the given links and campaigns."""
        az_campaign_by_id = {camp.Id: camp for camp in self.campaigns}
        az_creative_by_id = {creative.Id: creative
                             for creative in self.creatives}
        az_flight_by_id = {flight.Id: flight for flight in self.flights}

        for link, campaign in link_campaign_tuples:
            print 'reconciling %s %s with adzerk' % (link._fullname,
                                                     campaign._fullname)
            self.update_adzerk(link, campaign)

        for cfmap in self.cfmaps:
            if not cfmap.IsActive:
                 continue

            az_campaign = az_campaign_by_id[cfmap.CampaignId]
            az_creative = az_creative_by_id[cfmap.Creative.Id]
            az_flight = az_flight_by_id[cfmap.FlightId]

            link_fullname = az_campaign.Name
            link_fullname, campaign_fullname = az_creative.Title.split('-')
            campaign_fullname = az_flight.Name

            if (link_fullname, campaign_fullname) not in link_campaign_tuples:
                print 'deactivating %s (%s %s)' % (cfmap.Id, link_fullname,
                                                   campaign_fullname)
                cfmap.IsActive = False
                cfmap._send()

    def set_live_promotions(self, by_srid):
        # by_srid is the input to promote.set_live_promotions, so we'll use it
        # here for now. It is a dict {sr_id: [list of adweights]}. Adweights
        # are a namedtuple with the fields 'link', 'weight', 'campaign'
        link_fullnames = []
        campaign_fullnames = []

        for sr_id, adweights in by_srid.iteritems():
            link_fullnames.extend(a.link for a in adweights)
            campaign_fullnames.extend(a.campaign for a in adweights)

        links = Link._by_fullname(link_fullnames, data=True, return_dict=True)
        campaigns = PromoCampaign._by_fullname(campaign_fullnames, data=True,
                                               return_dict=True)

        link_campaign_tuples = []
        for adweight in itertools.chain(by_srid.itervalues()):
            link = links[adweight.link]
            campaign = campaigns[adweight.campaign]
            link_campaign_tuples.append((link, campaign))

        self.mirror(link_campaign_tuples)


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
# promotecontroller.py:
"""

def POST_update_pay():
    if g.authorizenetapi:
        success, reason = promote.auth_campaign(link, campaign, c.user, pay_id)

        if success:
            authorize.void_transaction(a, bid_record.transaction, campaign._id)


def something(offset=1):
    for l, campaign, weight in accepted_campaigns(offset=offset):
        

### local copy of things:
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.schema import Column
from sqlalchemy.sql.expression import desc, distinct
from sqlalchemy.sql.functions import sum as sa_sum
from sqlalchemy.types import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    TypeDecorator,
)

engine = g.dbm.get_engine("adzerk")
Session = scoped_session(sessionmaker(bind=engine, autocommit=True))
Base = declarative_base(bind=engine)

class AdzerkFlight(Base):
    __tablename__ = "adzerk_flight"
    Id = Column(Integer(), primary_key=True)
    Name = Column(String())
    Active = Column(Boolean())  # can this get changed on adzerk's end without our intervention? e.g. based on EndDate? If so we shouldn't include it
    # What do we want to use this for? If it's just a mapping of reddit thing to
    # adzerk thing then we can just add a data attribute to the reddit thing

"""