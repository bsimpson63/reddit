from r2.lib.db import tdb_cassandra
from r2.lib.utils import tup
from r2.models import Account, Subreddit, Link, Comment, Printable
from pycassa.system_manager import TIME_UUID_TYPE
from uuid import UUID
from pylons.i18n import _
from pylons import request

from pycassa.types import CompositeType, DateType, UTF8Type
from pycassa.util import convert_time_to_uuid
from pycassa.system_manager import DATE_TYPE, COUNTER_COLUMN_TYPE
from collections import defaultdict
import datetime

class ModAction(tdb_cassandra.UuidThing, Printable):
    """
    Columns:
    sr_id - Subreddit id36
    mod_id - Account id36 of moderator
    action - specific name of action, must be in ModAction.actions
    target_fullname - optional fullname of the target of the action
    details - subcategory available for some actions, must show up in 
    description - optional user
    """

    _use_db = True
    _connection_pool = 'main'
    _str_props = ('sr_id36', 'mod_id36', 'target_fullname', 'action', 'details', 
                  'description')
    _defaults = {}

    actions = ('banuser', 'unbanuser', 'removelink', 'approvelink', 
               'removecomment', 'approvecomment', 'addmoderator',
               'removemoderator', 'addcontributor', 'removecontributor',
               'editsettings', 'editflair', 'distinguish', 'marknsfw')

    _menu = {'banuser': _('ban user'),
             'unbanuser': _('unban user'),
             'removelink': _('remove post'),
             'approvelink': _('approve post'),
             'removecomment': _('remove comment'),
             'approvecomment': _('approve comment'),
             'addmoderator': _('add moderator'),
             'removemoderator': _('remove moderator'),
             'addcontributor': _('add contributor'),
             'removecontributor': _('remove contributor'),
             'editsettings': _('edit settings'),
             'editflair': _('edit user flair'),
             'distinguish': _('distinguish'),
             'marknsfw': _('mark nsfw')}

    _text = {'banuser': _('banned'),
             'unbanuser': _('unbanned'),
             'removelink': _('removed'),
             'approvelink': _('approved'),
             'removecomment': _('removed'),
             'approvecomment': _('approved'),                    
             'addmoderator': _('added moderator'),
             'removemoderator': _('removed moderator'),
             'addcontributor': _('added approved contributor'),
             'removecontributor': _('removed approved contributor'),
             'editsettings': _('edited settings'),
             'editflair': _('edited user flair'),
             'distinguish': _('distinguished'),
             'marknsfw': _('marked nsfw')}

    _details_text = {# approve comment/link
                     'unspam': _('unspam'),
                     # remove comment/link
                     'confirm_spam': _('confirmed spam'),
                     # removemoderator
                     'remove_self': _('removed self'),
                     # editsettings
                     'title': _('title'),
                     'description': _('description'),
                     'lang': _('language'),
                     'type': _('type'),
                     'link_type': _('link type'),
                     'over_18': _('toggle viewers must be over 18'),
                     'allow_top': _('toggle allow in default set'),
                     'show_media': _('toggle show thumbnail images of content'),
                     'domain': _('domain'),
                     'show_cname_sidebar': _('toggle show sidebar from cname'),
                     'css_on_cname': _('toggle custom CSS from cname'),
                     'header_title': _('header title'),
                     'stylesheet': _('stylesheet'),
                     'del_header': _('delete header image'),
                     'del_image': _('delete image'),
                     'upload_image_header': _('upload header image'),
                     'upload_image': _('upload image'),
                     # editflair
                     'flair_edit': _('add/edit flair'),
                     'flair_delete': _('delete flair'),
                     'flair_csv': _('edit by csv'),
                     'flair_enabled': _('toggle flair enabled'),
                     'flair_position': _('toggle flair position'),
                     'flair_self_enabled': _('toggle user assigned flair enabled'),
                     'flair_template': _('add/edit flair templates'),
                     'flair_delete_template': _('delete flair template'),
                     'flair_clear_template': _('clear flair templates'),
                     # distinguish/nsfw
                     'remove': _('remove')}

    # This stuff won't change
    cache_ignore = set(['subreddit', 'target']).union(Printable.cache_ignore)

    # Thing properties for Printable
    @property
    def author_id(self):
        return int(self.mod_id36, 36)

    @property
    def sr_id(self):
        return int(self.sr_id36, 36)

    @property
    def _ups(self):
        return 0

    @property
    def _downs(self):
        return 0

    @property
    def _deleted(self):
        return False

    @property
    def _spam(self):
        return False

    @property
    def reported(self):
        return False

    @classmethod
    def create(cls, sr, mod, action, details=None, target=None, description=None):
        # Split this off into separate function to check for valid actions?
        if not action in cls.actions:
            raise ValueError("Invalid ModAction: %s" % action)

        kw = dict(sr_id36=sr._id36, mod_id36=mod._id36, action=action)

        if target:
            kw['target_fullname'] = target._fullname
        if details:
            kw['details'] = details
        if description:
            kw['description'] = description

        ma = cls(**kw)
        ma._commit()
        return ma

    def _on_create(self):
        """
        Update all Views.
        """

        views = (ModActionBySR, ModActionBySRMod, ModActionBySRAction)

        for v in views:
            v.add_object(self)

    @classmethod
    def get_actions(cls, srs, mod=None, action=None, after=None, reverse=False, count=1000):
        """
        Get a ColumnQuery that yields ModAction objects according to
        specified criteria.
        """
        if after and isinstance(after, basestring):
            after = cls._byID(UUID(after))
        elif after and isinstance(after, UUID):
            after = cls._byID(after)

        if not isinstance(after, cls):
            after = None

        srs = tup(srs)

        if not mod and not action:
            rowkeys = [sr._id36 for sr in srs]
            q = ModActionBySR.query(rowkeys, after=after, reverse=reverse, count=count)
        elif mod and not action:
            rowkeys = ['%s_%s' % (sr._id36, mod._id36) for sr in srs]
            q = ModActionBySRMod.query(rowkeys, after=after, reverse=reverse, count=count)
        elif not mod and action:
            rowkeys = ['%s_%s' % (sr._id36, action) for sr in srs]
            q = ModActionBySRAction.query(rowkeys, after=after, reverse=reverse, count=count)
        else:
            raise NotImplementedError("Can't query by both mod and action")

        return q

    def get_extra_text(self):
        text = ''
        if hasattr(self, 'details') and not self.details == None:
            text += self._details_text.get(self.details, self.details)
        if hasattr(self, 'description') and not self.description == None:
            text += ' %s' % self.description
        return text

    @staticmethod
    def get_rgb(i, fade=0.8):
        r = int(256 - (hash(str(i)) % 256)*(1-fade))
        g = int(256 - (hash(str(i) + ' ') % 256)*(1-fade))
        b = int(256 - (hash(str(i) + '  ') % 256)*(1-fade))
        return (r, g, b)

    @classmethod
    def add_props(cls, user, wrapped):

        from r2.lib.menus import NavButton
        from r2.lib.db.thing import Thing
        from r2.lib.pages import WrappedUser
        from r2.lib.filters import _force_unicode

        TITLE_MAX_WIDTH = 50

        request_path = request.path

        target_fullnames = [item.target_fullname for item in wrapped if hasattr(item, 'target_fullname')]
        targets = Thing._by_fullname(target_fullnames, data=True)
        authors = Account._byID([t.author_id for t in targets.values() if hasattr(t, 'author_id')], data=True)
        links = Link._byID([t.link_id for t in targets.values() if hasattr(t, 'link_id')], data=True)
        subreddits = Subreddit._byID([item.sr_id for item in wrapped], data=True)

        # Assemble target links
        target_links = {}
        target_accounts = {}
        for fullname, target in targets.iteritems():
            if isinstance(target, Link):
                author = authors[target.author_id]
                title = _force_unicode(target.title)
                if len(title) > TITLE_MAX_WIDTH:
                    short_title = title[:TITLE_MAX_WIDTH] + '...'
                else:
                    short_title = title
                text = '%(link)s "%(title)s" %(by)s %(author)s' % {
                        'link': _('link'),
                        'title': short_title, 
                        'by': _('by'),
                        'author': author.name}
                path = target.make_permalink(subreddits[target.sr_id])
                target_links[fullname] = (text, path, title)
            elif isinstance(target, Comment):
                author = authors[target.author_id]
                link = links[target.link_id]
                title = _force_unicode(link.title)
                if len(title) > TITLE_MAX_WIDTH:
                    short_title = title[:TITLE_MAX_WIDTH] + '...'
                else:
                    short_title = title
                text = '%(comment)s %(by)s %(author)s %(on)s "%(title)s"' % {
                        'comment': _('comment'),
                        'by': _('by'),
                        'author': author.name,
                        'on': _('on'),
                        'title': short_title}
                path = target.make_permalink(link, subreddits[link.sr_id])
                target_links[fullname] = (text, path, title)
            elif isinstance(target, Account):
                target_accounts[fullname] = WrappedUser(target)

        for item in wrapped:
            # Can I move these buttons somewhere else? Not great to have request stuff in here
            css_class = 'modactions %s' % item.action
            item.button = NavButton('', item.action, opt='type', css_class=css_class)
            item.button.build(base_path=request_path)

            mod_name = item.author.name
            item.mod = NavButton(mod_name, mod_name, opt='mod')
            item.mod.build(base_path=request_path)
            item.text = ModAction._text.get(item.action, '')
            item.details = item.get_extra_text()

            if hasattr(item, 'target_fullname') and item.target_fullname:
                target = targets[item.target_fullname]
                if isinstance(target, Account):
                    item.target_wrapped_user = target_accounts[item.target_fullname]
                elif isinstance(target, Link) or isinstance(target, Comment):
                    item.target_text, item.target_path, item.target_title = target_links[item.target_fullname]

            item.bgcolor = ModAction.get_rgb(item.sr_id)
            item.sr_name = subreddits[item.sr_id].name
            item.sr_path = subreddits[item.sr_id].path

        Printable.add_props(user, wrapped)

class ModActionBySR(tdb_cassandra.View):
    _use_db = True
    _connection_pool = 'main'
    _compare_with = TIME_UUID_TYPE
    _view_of = ModAction
    _ttl = 60*60*24*30*3  # 3 month ttl

    @classmethod
    def _rowkey(cls, ma):
        return ma.sr_id36

class ModActionBySRMod(tdb_cassandra.View):
    _use_db = True
    _connection_pool = 'main'
    _compare_with = TIME_UUID_TYPE
    _view_of = ModAction
    _ttl = 60*60*24*30*3  # 3 month ttl

    @classmethod
    def _rowkey(cls, ma):
        return '%s_%s' % (ma.sr_id36, ma.mod_id36)

class ModActionBySRAction(tdb_cassandra.View):
    _use_db = True
    _connection_pool = 'main'
    _compare_with = TIME_UUID_TYPE
    _view_of = ModAction
    _ttl = 60*60*24*30*3  # 3 month ttl

    @classmethod
    def _rowkey(cls, ma):
        return '%s_%s' % (ma.sr_id36, ma.action)

class ModActionHistory(tdb_cassandra.View):
    _use_db = True
    _connection_pool = 'main'
    _value_type = 'int'
    _compare_with = CompositeType(DateType(), UTF8Type(), UTF8Type())
    _timestamp_prop = None
    _ttl = 60*60*24*30*3

    @classmethod
    def _rowkey(cls, ma):
        return ma.sr_id36

    # Columns are objects are columns
    @classmethod
    def _column_to_obj(cls, columns):
        for c in columns:
            for k,v in c.iteritems():
                c[k] = cls._deserialize_column(k, v)
        return columns

    @classmethod
    def _obj_to_column(cls, objs):
        return objs

    @staticmethod
    def _date_only(date):
        if isinstance(date, datetime.datetime):
            date = date.date()
        return datetime.datetime.combine(date, datetime.time())

    @classmethod
    def get_day(cls, sr, date):
        date = cls._date_only(date)
        rowkey = sr._id36
        d = defaultdict(int)

        q = cls.query(rowkey)
        q.column_start = (date + datetime.timedelta(days=1),)
        q.column_finish = (date,)
        columns = list(q)
        while columns:
            for c in columns:
                for (date, mod_id36, action),v in c.iteritems():
                    key = (mod_id36, action)
                    d[key] = v
            q._after(columns[-1])
            columns = list(q)
        return d

    @classmethod
    def get_report(cls, sr, start_date, end_date):
        d = defaultdict(int)
        start_date = cls._date_only(start_date)
        end_date = cls._date_only(end_date)
        current_date = start_date
        delta = datetime.timedelta(days=1)
        while current_date <=  end_date:
            d_new = cls.get_day(sr, current_date)
            for k,v in d_new.iteritems():
                d[k] += v
            current_date += delta
        return d

    @classmethod
    def _query_all_srs(cls, date):
        CHUNK_SIZE = 1000
        actions_by_sr = {}
        date = cls._date_only(date)

        start_uuid = convert_time_to_uuid(date)
        end_uuid = convert_time_to_uuid(date + datetime.timedelta(days=1))
        view_cls = ModActionBySR

        q = tdb_cassandra.RangeQuery(view_cls, column_start=end_uuid,
                                     column_finish=start_uuid,
                                     column_reversed=True,
                                     column_to_obj=view_cls._column_to_obj,
                                     obj_to_column=view_cls._obj_to_column,
                                     column_count=CHUNK_SIZE)
        actions = list(q)
        while actions:
            for ma in actions:
                sr_id36 = ma.sr_id36
                key = (date, ma.mod_id36, ma.action)
                actions_by_sr.setdefault(sr_id36, defaultdict(int))[key] += 1

            q._after(actions[-1])
            actions = list(q)

        return actions_by_sr

    @classmethod
    def _write_all_srs(cls, date=None):
        if not date:
            date = datetime.datetime.now(g.tz)

        actions_by_sr = cls._query_all_srs(date)
        for sr_id36, columns in actions_by_sr.iteritems():
            cls._set_values(sr_id36, columns)

    @classmethod
    def test(cls):
        today = datetime.datetime.now()
        earliest = today - datetime.timedelta(days=90)
        delta = datetime.timedelta(days=1)
        r = defaultdict(dict)
        current = earliest
        while current <= today:
            print 'Fetching %s' % current
            for k,v in ModActionHistory._query_all_srs(current).iteritems():
                r[k].update(v)
            current += delta
        return r

    @classmethod
    def write_history(cls):
        today = datetime.datetime.now()
        earliest = today - datetime.timedelta(days=90)
        delta = datetime.timedelta(days=1)
        current = earliest
        while current <= today:
            print 'Writing %s' % current
            ModActionHistory._write_all_srs(current)
            current += delta
