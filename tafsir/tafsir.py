import re
import re
import textwrap

import discord
import fuzzywuzzy
from discord.ext import commands
from fuzzywuzzy import process, fuzz

from quran.quran_info import Surah, QuranReference
from utils.errors import InvalidTafsir, respond_to_interaction_error
from utils.slash_utils import get_key_from_value
from utils.utils import get_site_source, get_site_json

icon = 'https://cdn6.aptoide.com/imgs/6/a/6/6a6336c9503e6bd4bdf98fda89381195_icon.png'

name_mappings = {
    'maarifulquran': 'Maarif-ul-Quran',
    'ibnkathir': 'Tafsīr Ibn Kathīr',
    'jalalayn': 'Tafsīr al-Jalālayn',
    'tustari': 'Tafsīr al-Tustarī',
    'kashani': 'Tafsīr ʿAbd al-Razzāq al-Kāshānī',
    'qushayri': 'Laṭāʾif al-Ishārāt',
    'wahidi': 'Asbāb al-Nuzūl',
    'kashf': 'Kashf al-Asrār',
    'saddi': "Tafsīr al-Sa'di (Russian)",
    'zakaria': 'Tafsir Abu Bakr Zakaria (Bengali)',
    "israr": "تفسیر بیان القرآن",
    "ibnkathir.ur": "تفسیر ابنِ کثیر",
    'ibnkathir.bn': 'তাফসীর ইবনে কাছী',
    'mukhtasar': 'Al-Mukhtasar',
    'ahsanul': 'Tafsir Ahsanul Bayaan'
}

name_alias = {
    "saadi": "saddi",  # saadi is more correct ( السعدي )
    "jalalain": "jalalayn",  # jalalaIn is AlTafsir's spelling
    "asbabalnuzul": "wahidi",  # better known name
    "asbab": "wahidi",  # better known name, shortened
}

altafsir_sources = {
    'tustari': 93,
    'kashani': 107,
    'qushayri': 108,
    'wahidi': 86,
    'kashf': 109,
}

quranCom_sources = {
    'ibnkathir': 169,
    'ibnkathir.ur': 160,
    'ibnkathir.bn': 164,
    'maarifulquran': 168,
    'saddi': 170,
    'mukhtasar': 171,
    'ahsanul': 165,
    'zakaria': 166,
    'israr': 159,
}

NO_TEXT = "**Could not find tafsir for this verse.** Please try another tafsir." \
          "\n\n**List of tafasir**: <https://github.com/galacticwarrior9/IslamBot/wiki/Tafsir-List>."

BAD_ALIAS = "This is normally unreachable error! Developer, please check aliases for tafsir!"

ALTAFSIR_URL = 'https://www.altafsir.com/Tafasir.asp?tMadhNo=0&tTafsirNo={}&tSoraNo={}&tAyahNo={}&tDisplay=yes&Page={}&Size=1&LanguageId=2'

QURAN_COM_URL = 'https://api.quran.com/api/v4/tafsirs/{}/by_ayah/{}'

JALALAYN_URL = 'https://raw.githubusercontent.com/galacticwarrior9/islambot/master/tafsir/tafsir_jalalayn.txt'

CLEAN_HTML_REGEX = re.compile('<(.*?)>')


class NoText(commands.CommandError):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class BadAlias(commands.CommandError):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class TafsirRequest:
    def __init__(self, tafsir, ref, page, reveal_order: bool = False):
        self.pages = None
        self.num_pages = None
        self.url = None
        self.tafsir_author = None
        self.text = None
        self.embed = None
        self.page = page

        self.query_tafsir(tafsir)

        self.ref = QuranReference(ref=ref, reveal_order=reveal_order)
        self.make_url()

    # this is the function to implement better tafsir retrieval
    def query_tafsir(self, t):
        try:
            assert (len(t) > 0)
        except:
            raise InvalidTafsir

        t = t.lower()

        # 95% of tafsirs should be found here
        if t in name_mappings.keys():
            self.tafsir = t
            self.tafsir_name = name_mappings[t]
            return

        # if not, try aliases
        if t in name_alias.keys():
            buf = name_alias[t]
            # I assume aliases are set up correctly, if not raise normally unreachable error
            if buf not in name_mappings.keys():
                raise BadAlias

            self.tafsir = buf
            self.tafsir_name = name_mappings[buf]
            return

        # IF all failed, raise an error
        raise InvalidTafsir

    def make_url(self):
        if self.tafsir in altafsir_sources.keys():
            tafsir_id = altafsir_sources[self.tafsir]
            self.url = ALTAFSIR_URL.format(tafsir_id, self.ref.surah, self.ref.ayat_list, 1)
        elif self.tafsir == 'jalalayn':
            self.url = JALALAYN_URL
        elif self.tafsir in quranCom_sources.keys():
            tafsir_id = quranCom_sources[self.tafsir]
            self.url = QURAN_COM_URL.format(tafsir_id, f'{self.ref.surah}:{self.ref.ayat_list}')

    async def get_text(self):
        if self.tafsir in altafsir_sources.keys():
            source = await get_site_source(self.url)
            tags = []
            for tag in source.findAll('font', attrs={'class': 'TextResultEnglish'}):
                tags.append(f' {tag.getText()}')
            for tag in source.findAll('font', attrs={'class': 'TextArabic'}):
                tags.append(tag.getText())
            self.text = ''.join(tags)

        elif self.tafsir in quranCom_sources.keys():
            source = await get_site_json(self.url)
            self.text = source['tafsir']['text']
            self.tafsir_author = source['tafsir']['translated_name']['name']

            # Replace HTML tags
            self.text = re.sub(CLEAN_HTML_REGEX, ' ', self.text)
            self.text = self.text.replace('`', "ʿ")

        elif self.tafsir == 'jalalayn':
            source = await get_site_source(self.url)
            source = source.decode('utf-8')
            self.tafsir_author = 'Jalal ad-Din al-Maḥalli and Jalal ad-Din as-Suyuti'

            try:
                char1 = f'[{self.ref.surah}:{self.ref.ayat_list}]'
                next_ayah = self.ref.ayat_list + 1
                char2 = f'[{self.ref.surah}:{next_ayah}]'

                text = source[(source.index(char1) + len(char1)):source.index(char2)]
                self.text = f"{text}".replace('`', '\\`').replace('(s)', '(ﷺ)').rstrip()

            except:
                char1 = f'[{self.ref.surah}:{self.ref.surah}]'
                self.ref.surah += 1
                char2 = f'[{self.ref.surah}:1]'

                text = source[(source.index(char1) + len(char1)):source.index(char2)]
                self.text = u"{}".format(text).replace('`', '\\`').rstrip()

        self.pages = textwrap.wrap(self.text, 2000, break_long_words=False)
        self.num_pages = len(self.pages)

    def make_embed(self):
        em = discord.Embed(colour=0x467f05, description=self.pages[self.page - 1])
        em.title = f'Tafsir of Surah {Surah(self.ref.surah).name}, Verse {self.ref.ayat_list}'
        em.set_author(name=self.tafsir_name, icon_url=icon)

        if self.num_pages > 1:
            if self.tafsir_author is None:
                em.set_footer(text=f'Page: {self.page}/{self.num_pages}')
            else:
                em.set_footer(text=f'Author: {self.tafsir_author}\nPage: {self.page}/{self.num_pages}')
        elif self.tafsir_author is not None:
            em.set_footer(text=f'Author: {self.tafsir_author}')

        self.embed = em


class Tafsir(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_embed(self, interaction: discord.Interaction, spec: TafsirRequest):
        if spec.num_pages == 1:
            return await interaction.followup.send(embed=spec.embed)
        else:
            tafsir_ui_view = TafsirNavigator(spec)
            await interaction.followup.send(embed=spec.embed, view=tafsir_ui_view)

    async def process_request(self, ref: str, tafsir: str, page: int, reveal_order: bool = False):
        spec = TafsirRequest(tafsir=tafsir, ref=ref, page=page, reveal_order=reveal_order)
        try:
            await spec.get_text()
        except IndexError:
            # If no entry was found in the default tafsir (Maarif-ul-Quran), fall back to Tafsir al-Jalalayn.
            if tafsir == 'maarifulquran':
                return await self.process_request(ref=ref, tafsir='jalalayn', page=page, reveal_order=reveal_order)
            else:
                raise NoText

        if len(spec.text) == 0:
            raise NoText

        spec.make_embed()
        return spec

    @discord.app_commands.command(name="tafsir", description="Get the tafsir of a Qur'anic verse.")
    @discord.app_commands.describe(
        surah="The name or number of the verse's surah, e.g. Al-Ikhlaas or 112.",
        verse_number="The verse number to fetch.",
        tafsir_name="The name of the tafsir to use.",
    )
    async def tafsir(self, interaction: discord.Interaction, surah: str, verse_number: int,
                     tafsir_name: str = "maarifulquran"):
        await interaction.response.defer()
        surah_number = QuranReference.parse_surah_number(surah)
        tafsir_request = await self.process_request(ref=f'{surah_number}:{verse_number}', tafsir=tafsir_name, page=1)
        await self.send_embed(interaction, tafsir_request)

    @tafsir.autocomplete('tafsir_name')
    async def tafsir_autocomplete_callback(self, interaction: discord.Interaction, current: str):
        closest_matches = [match[0] for match in process.extract(current, name_mappings.values(), scorer=fuzz.token_sort_ratio, limit=5)]
        choices = [discord.app_commands.Choice(name=match, value=get_key_from_value(match, name_mappings)) for match in closest_matches]
        return choices

    @tafsir.error
    async def on_tafsir_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        if isinstance(error, NoText):
            await interaction.followup.send(NO_TEXT)
        elif isinstance(error, BadAlias):
            await interaction.followup.send(BAD_ALIAS)
        else:
            await respond_to_interaction_error(interaction, error)


class TafsirNavigator(discord.ui.View):
    def __init__(self, tafsir: TafsirRequest):
        super().__init__()
        self.tafsir = tafsir

    @discord.ui.button(label='Previous Page', style=discord.ButtonStyle.red, emoji='⬅')
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.tafsir.page > 1:
            self.tafsir.page -= 1
        else:
            self.tafsir.page = self.tafsir.num_pages
        self.tafsir.make_embed()
        await interaction.response.edit_message(embed=self.tafsir.embed)

    @discord.ui.button(label='Next Page', style=discord.ButtonStyle.green, emoji='➡')
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.tafsir.page < self.tafsir.num_pages:
            self.tafsir.page += 1
        else:
            self.tafsir.page = 1
        self.tafsir.make_embed()
        await interaction.response.edit_message(embed=self.tafsir.embed)


async def setup(bot):
    await bot.add_cog(Tafsir(bot), guild=discord.Object(308241121165967362))
