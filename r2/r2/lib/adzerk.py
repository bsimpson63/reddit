import json
import requests


API_KEY = ''


def set_key(key):
    import sys
    setattr(sys.modules[__name__], 'API_KEY', key)


class AdzerkError(Exception): pass
class NotFound(AdzerkError): pass


def handle_response(response):
    if response.status_code == 400:
        raise NotFound
    elif response.status_code != 200:
        raise AdzerkError('response %s' % response.status_code)
    try:
        return json.loads(response.text)
    except ValueError:
        raise AdzerkError('bad response')


goal_types = {
    1: 'Impressions',
    2: 'Percentage',
    3: 'Click',
    4: 'Even',
    5: 'View Conversions',
    6: 'Click Conversions',
    7: 'Any Conversions',
}

rate_types = {
    1: 'Flat',
    2: 'CPM',
    3: 'CPC',
    4: 'CPA View',
    5: 'CPA Click',
    6: 'CPA Both',
}

freq_cap_types = {
    1: 'Hour',
    2: 'Day',
}


class Base(object):
    _name = ''
    _base_url = 'http://api.adzerk.net/v1'
    _attr_map = ()
    _optional = set()

    @classmethod
    def _headers(cls):
        return {'X-Adzerk-ApiKey': API_KEY,
                'Content-Type': 'application/x-www-form-urlencoded'}

    def __init__(self, id, **attr):
        self.id = id
        for attr, val in attr.iteritems():
            setattr(self, attr, val)

    @classmethod
    def _from_items(cls, items):
        r = []
        for item in items:
            id = item['Id']
            attrs = {}
            for remote, local in cls._attr_map:
                if local not in cls._optional or item.has_key(remote):
                    attrs[local] = item[remote]
            thing = cls(id, **attrs)
            r.append(thing)
        return r

    def _to_item(self):
        item = {'Id': self.id}
        for remote, local in self._attr_map:
            if local not in self._optional or hasattr(self, local):
                item[remote] = getattr(self, local)
        return item

    def _to_data(self):
        return '%s=%s' % (self._name, json.dumps(self._to_item()))

    @classmethod
    def list(cls):
        url = '/'.join([cls._base_url, cls._name])
        response = requests.get(url, headers=cls._headers())
        content = handle_response(response)
        if content['Items']:
            return cls._from_items(content['Items'])

    @classmethod
    def create(cls, **attr):
        url = '/'.join([cls._base_url, cls._name])
        missing = set([local for remote, local in cls._attr_map])
        missing -= cls._optional
        missing -= set(attr.keys())
        if missing:
            missing = ', '.join(missing)
            raise ValueError("missing required attributes: %s" % missing)
        thing = cls(None, **attr)
        data = thing._to_data()
        response = requests.post(url, headers=cls._headers(), data=data)
        item = handle_response(response)
        return cls._from_items([item])[0]

    def _send(self):
        url = '/'.join([self._base_url, self._name, str(self.id)])
        data = self._to_data()
        response = requests.put(url, headers=self._headers(), data=data)

    def update(self, **updates):
        url = '/'.join([self._base_url, self._name, str(self.id)])
        originals = {}
        for attr, val in updates.iteritems():
            originals[attr] = getattr(self, attr)
            setattr(self, attr, val)
        data = self._to_data()
        response = requests.put(url, headers=self._headers(), data=data)
        try:
            item = handle_response(response)
        except AdzerkError:
            for attr, val in orignals.iteritems():
                setattr(self, attr, val)
            raise
        # return self? either modify self and don't return, or return new modified object

    @classmethod
    def get(cls, id):
        url = '/'.join([cls._base_url, cls._name, str(id)])
        response = requests.get(url, headers=cls._headers())
        item = handle_response(response)
        return cls._from_items([item])[0]


class Site(Base):
    _name = 'site'
    _attr_map = (
        ('Url', 'url'),
        ('Title', 'title'),
    )

    def __repr__(self):
        return '<Site %s <%s-%s>>' % (self.id, self.title, self.url)


class Zone(Base):
    _name = 'zone'
    _attr_map = (
        ('Name', 'name'),
        ('SiteId', 'site_id'),
    )

    def __repr__(self):
        return '<Zone %s <%s on %s>>' % (self.id, self.name, self.site_id)


class Advertiser(Base):
    _name = 'advertiser'
    _attr_map = (
        ('Title', 'name'),
    )

    @classmethod
    def search(cls, name):
        raise NotImplementedError

    def __repr__(self):
        return '<Advertiser %s <%s>>' % (self.id, self.name)


class Flight(Base):
    _name = 'flight'
    _attr_map = (
        ('StartDate', 'start_date'),
        ('EndDate', 'end_date'),
        ('NoEndDate', 'no_end_date'),
        ('Price', 'price'),
        ('OptionType', 'option_type'),  # 1 - CPM, 2- Remainder
        ('Impressions', 'impressions'),
        ('IsUnlimited', 'is_unlimited'), # bool: override Impressions
        ('IsNoDuplicates', 'is_no_duplicates'),
        ('IsFullSpeed', 'is_full_speed'),   # bool: serve fast as possible
        ('Keywords', 'keywords'),
        ('UserAgentKeywords', 'user_agent_keywords'),
        ('CampaignId', 'campaign_id'),
        ('PriorityId', 'priority_id'),
        ('IsDeleted', 'is_deleted'),
        ('IsActive', 'is_active'),
        ('GoalType', 'goal_type'),
        ('RateType', 'rate_type'),
        ('IsFreqCap', 'is_freq_cap'),
        ('FreqCap', 'freq_cap'),
        ('FreqCapDuration', 'freq_cap_duration'),
        ('FreqCapType', 'freq_cap_type'),
        ('DatePartingStartTime', 'date_parting_start_time'),
        ('DatePartingEndTime', 'date_parting_end_time'),
        ('IsSunday', 'is_sunday'),
        ('IsMonday', 'is_monday'),
        ('IsTuesday', 'is_tuesday'),
        ('IsWednesday', 'is_wednesday'),
        ('IsThursday', 'is_thursday'),
        ('IsFriday', 'is_friday'),
        ('IsSaturday', 'is_saturday'),
    )
    _optional = {'end_date', 'no_end_date', 'goal_type', 'rate_type', 
                 'is_freq_cap', 'freq_cap', 'freq_cap_duration',
                 'freq_cap_type', 'keywords', 'user_agent_keywords',
                 'date_parting_start_time', 'date_parting_end_time',
                 'is_sunday', 'is_monday', 'is_tuesday', 'is_wednesday',
                 'is_thursday', 'is_friday', 'is_saturday'}

    @property
    def frequency_cap(self):
        if not self.is_freq_cap:
            return None
        return '%s per %s %s' % (self.freq_cap, self.freq_cap_duration,
                                 freq_cap_types[self.freq_cap_type])

    def set_daily_cap(self, impressions):
        self.is_freq_cap = True
        self.freq_cap_type = 2
        self.freq_cap = impressions
        self.freq_cap_duration = 1

    def __repr__(self):
        return '<Flight %s <Campaign %s>>' % (self.id, self.campaign_id)


class Priority(Base):
    _name = 'priority'
    _attr_map = (
        ('Name', 'name'),
        ('ChannelId', 'channel_id'),
        ('Weight', 'weight'),
        ('IsDeleted', 'is_deleted'),
    )

    def __repr__(self):
        return '<Priority %s <Weight %s - Channel %s>>' % (self.id, self.weight,
                                                           self.channel_id)

class Channel(Base):
    _name = 'channel'
    _attr_map = (
        ('Title', 'name'),
        ('Commission', 'commission'),
        ('Engine', 'engine'),
        ('Keywords', 'keywords'),   # comma separated string
        ('CPM', 'cpm'),
        ('AdTypes', 'ad_types')
    )

    def __repr__(self):
        return '<Channel %s>' % (self.id)


class Campaign(Base):
    _name = 'campaign'
    _attr_map = (
        ('Name', 'name'),
        ('AdvertiserId', 'advertiser_id'),
        ('Flights', 'flights'),
        ('StartDate', 'start_date'),
        ('EndDate', 'end_date'),
        ('IsDeleted', 'is_deleted'),
        ('IsActive', 'is_active'),
        ('Price', 'price'),
    )
    _optional = {'end_date'}

    @classmethod
    def _from_items(cls, items):
        for item in items:
            if not 'Flights' in item:
                item['Flights'] = []
        things = super(cls, cls)._from_items(items)
        for thing in things:
            if hasattr(thing, 'flights'):
                thing.flights = Flight._from_items(thing.flights)
        return things

    def _to_item(self):
        item = Base._to_item(self)
        flights = item.get('Flights')
        if flights:
            item['Flights'] = [flight._to_item() for flight in flights]
        return item

    def __repr__(self):
        return '<Campaign %s>' % (self.id)
