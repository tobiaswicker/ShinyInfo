import json
import logging
import os
import pickle
import urllib.request
from collections import OrderedDict

import requests

from lxml import html

logger = logging.getLogger(__name__)


class Shiny:
    """Data structure for details on shiny pokémon"""
    def __init__(self, dex_id, wild=None, raid=None, evolution=None, egg=None, research=None, mystery=None):
        self.dex_id = dex_id
        self.wild = wild
        self.raid = raid
        self.evolution = evolution
        self.egg = egg
        self.research = research
        self.mystery = mystery

    def __eq__(self, other):
        return self.dex_id == other.dex_id and \
               self.wild == other.wild and \
               self.raid == other.raid and \
               self.evolution == other.evolution and \
               self.egg == other.egg and \
               self.research == other.research and \
               self.mystery == other.mystery

    def __repr__(self):
        params = ", ".join(f"{key}={value}" for key, value in self.__dict__.items() if value is not None)
        return f"{self.__class__.__name__}({params})"


class ShinyManager:
    """Manager for shinies from various data sources. This is a Singleton."""
    _instance = None
    _initialized = False
    _shiny_data_file = 'shiny_data.pickle'
    _emoji = {
        'wild': '🐾',
        'raid': '⚔️',
        'evolution': '🧿',
        'egg': '🥚',
        'research': '🔍',
        'mystery': '🎁'
    }

    supported_sites = ['pogoapi.net', 'gamepress.gg']

    def __new__(cls, *args, **kwargs):
        # make sure only one instance exists
        if not ShinyManager._instance:
            ShinyManager._instance = object.__new__(cls)
        return ShinyManager._instance

    def __init__(self):
        # only init if instance hasn't been initialized yet
        if not ShinyManager._initialized:
            ShinyManager._initialized = True

            self._shinies = {}
            self._new_shinies = {}
            self._changed_shinies = {}
            self._load_shinies_from_file()

    def _load_shinies_from_file(self):
        """Load shiny info from file"""
        if os.path.isfile(self._shiny_data_file):
            with open(self._shiny_data_file, 'rb') as f:
                self._shinies = pickle.load(f)

    def _store_shinies_to_file(self):
        """Store shiny info in a file"""
        with open(self._shiny_data_file, 'wb') as f:
            pickle.dump(self._shinies, f)

    @staticmethod
    def _load_shinies_pogoapi_net():
        """Load all shiny pokemon from pogoapi.net"""
        shiny_list = {}

        url = "https://pogoapi.net//api/v1/shiny_pokemon.json"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())

            for dex_id, shiny_data in data.items():
                dex_id = int(dex_id)

                if dex_id in shiny_list:
                    logger.warning("Possible duplicate for dex id {dex_id} found while parsing data from pogoapi.net.")

                shiny = Shiny(dex_id)
                shiny.wild = 'found_wild' in shiny_data and shiny_data['found_wild']
                shiny.raid = 'found_raid' in shiny_data and shiny_data['found_raid']
                shiny.evolution = 'found_evolution' in shiny_data and shiny_data['found_evolution']
                shiny.egg = 'found_egg' in shiny_data and shiny_data['found_egg']

                shiny_list[dex_id] = shiny

        return shiny_list

    @staticmethod
    def _load_shinies_gamepress_gg():
        """Load all shiny pokemon from gamepress.gg"""
        url = 'https://pokemongo.gamepress.gg/pokemon-go-shinies-list'
        raw = requests.get(url)
        data = html.fromstring(raw.content)

        shiny_result = {}

        # mapping of html classes for shinies to Shiny class attributes
        class_mapping = {'Raids': 'raid',
                         'Wild': 'wild',
                         'Nesting': 'wild',
                         'Evolution': 'evolution',
                         'Eggs': 'egg',
                         'Research': 'research',
                         'Mystery': 'mystery'}

        for html_class, class_attr in class_mapping.items():
            # find links to pokemon
            shiny_links = data.xpath(f"//tr[contains(@class, '{html_class}')]//a")

            for link_tag in shiny_links:
                # get dex id
                link = link_tag.attrib['href']
                dex_id = int("".join(digit for digit in link if digit.isdigit()))

                # create a new shiny if shiny doesn't exist yet
                if dex_id not in shiny_result:
                    shiny = Shiny(dex_id=dex_id,
                                  wild=False,
                                  raid=False,
                                  evolution=False,
                                  egg=False,
                                  research=False,
                                  mystery=False)
                    setattr(Shiny, class_attr, True)
                    shiny_result[dex_id] = shiny
                # modify existing shiny
                else:
                    setattr(shiny_result[dex_id], class_attr, True)

        return shiny_result

    def _load_shinies(self, site):
        """Load all shinies from a given site"""
        logger.debug(f"Loading shinies from {site}...")

        site_method = f"_load_shinies_{site.replace('.', '_')}"

        # check if getter for site exists
        if not hasattr(self, site_method):
            raise Exception(f"Getting shinies from {site} is not supported.")

        # reset or create new and changed shiny dict
        self._new_shinies[site] = {}
        self._changed_shinies[site] = {}
        # get shinies
        shiny_loader = getattr(self, site_method)
        shiny_result = shiny_loader()
        logger.debug(f"Retrieved {len(shiny_result)} shinies from {site}.")

        if site not in self._shinies:
            self._shinies[site] = {}

        for dex_id, shiny in shiny_result.items():
            # check if shiny is known
            if dex_id not in self._shinies[site]:
                self._new_shinies[site][dex_id] = shiny
            # check if shiny info has changed
            elif shiny != self._shinies[site][dex_id]:
                changed_attributes = {}
                for attr in shiny.__dict__.keys():
                    if getattr(shiny, attr) != getattr(self._shinies[site][dex_id], attr):
                        changed_attributes[attr] = [getattr(self._shinies[site][dex_id], attr), getattr(shiny, attr)]

                self._changed_shinies[site][dex_id] = changed_attributes

        ordered_result = OrderedDict(sorted(shiny_result.items()))

        # remember result for comparision later on
        self._shinies[site] = ordered_result

    def load_all_shinies(self):
        """Load all shinies from all sites"""
        logger.debug("Loading all shinies...")

        # clear info about new / changed shinies
        self._new_shinies = {}
        self._changed_shinies = {}

        # load all shinies
        for site in ShinyManager.supported_sites:
            self._load_shinies(site)

        # store shinies
        self._store_shinies_to_file()

        if any(self._new_shinies.values()):
            logger.info(f"New shinies found: {self._new_shinies}")
        if any(self._changed_shinies.values()):
            logger.info(f"Changed shinies found: {self._changed_shinies}")

    def get_shinies(self, site):
        """Get shinies for a given site"""
        return self._shinies.get(site, {})

    def get_all_new_shinies(self):
        """Get all new shinies"""
        return self._new_shinies

    def get_all_changed_shinies(self):
        """Get all changed shinies"""
        return self._changed_shinies

    def get_emojis_for_shiny(self, shiny: Shiny):
        return "".join(self.get_emoji(attr) for attr in shiny.__dict__.keys() if getattr(shiny, attr))

    def get_emoji(self, attr):
        return self._emoji.get(attr, '')

