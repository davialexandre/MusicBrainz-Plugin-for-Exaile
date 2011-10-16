# Author: Davi Alexandre
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

from xl import event
import gtk, gobject
import glib
import os, re
from musicbrainz2.webservice import Query, TrackFilter, WebServiceError
from xl.nls import gettext as _

def enable(exaile):
	if(exaile.loading):
		event.add_callback(__enb, 'gui_loaded')
	else:
		__enb(None, exaile, None)
	
def disable(exaile):
	global PLUGIN
	PLUGIN.disable()
	PLUGIN = None
	
def __enb(eventname, exaile, nothing):
	gobject.idle_add(_enable, exaile)
	
def _enable(exaile):
	global PLUGIN
	PLUGIN = MusicBrainzPlugin(exaile)

class MusicBrainzTrackSearch:
	"""
		Searches MusicBrainz database for Suggestions based on a Track
	"""
	def __init__(self):
		self.query = Query()

	def _build_musicbrainz_query(self, track):
		"""
			Build a query string in Lucene Format.

			track: The Track object wich values will be used to build
			the query
		"""
		tags = {
			'release': 'album',
			'artist': 'artist',
			'tnum': 'tracknumber',
			'track': 'title'
		}
		query_params = []
		for musicbrainz_tag, exaile_tag in tags.iteritems():
			tag_value = track.get_tag(exaile_tag)
			if tag_value:
				query_params.append(musicbrainz_tag + ":("+ tag_value[0] +")")
		query = ' '.join(query_params)
		return query

	def get_tracks_suggestions(self, track):
		"""
			Fetch track suggestions from Musicbrainz WebService

			track: The Track object wich values will be used in the query
		"""
		query = self._build_musicbrainz_query(track)
		filter = TrackFilter(query = query)
		tracks_result = self.query.getTracks(filter)
		return tracks_result


class MusicBrainzPlugin:
	"""
		The MusicBrainz Plugin enables exaile to search Musicbrainz
		database for suggestions to fill in ID3 tags of a selected track

		This plugin shows a list with track suggestions where the user
		can select the best fit to the selected track
	"""

	# The messages to use with some errors
	WS_ERROR_MESSAGE = 'Error, getting tracks suggestions. \nPlease, check your connection and try again.'
	SELECT_TRACK_ERROR_MESSAGE = 'You need to select a suggestion.'
	
	def __init__(self, exaile):
		self.exaile = exaile
		self.track_search = MusicBrainzTrackSearch()
		self.columns_titles = [
			_('Score'),
			_('Artist'),
			_('Title'),
			_('Album'),
			_('Album Type'),
			_('Track #')
		]
		self.columns_widths = [40, 200, 250, 250, 80, 50]
		playlist_menu = self._get_current_playlist_menu()
		self._load_glade_dialog()
		if playlist_menu:
			#check if there's a menu to put the item on
			#from this menu item whe show the track suggestions list
			self._add_menu_item(playlist_menu)

	def _load_glade_dialog(self):
		"""
			Load and prepare the "Track Suggestion" and "Loading" dialogs
		"""
		PATH = os.path.dirname(os.path.realpath(__file__))

		loadingdialog_xml = os.path.join(PATH,'loading_dialog.glade')
		self.loading_dialog = gtk.glade.XML(loadingdialog_xml).get_widget('loading_window')

		trackssuggestions_xml = os.path.join(PATH,'tracksuggestions_dialog.glade')
		self.glade_xml = gtk.glade.XML(trackssuggestions_xml)
		self.glade_xml.signal_autoconnect(self)
		
		self.dialog	= self.glade_xml.get_widget('track_suggestions')
		self.label = self.glade_xml.get_widget('lbl_instruction')
		self.tracks_list = self.glade_xml.get_widget('tracks_list')
		
		self.label.set_label(_('Select one suggestion and press "Save" to fill in the tags'))
		self._add_list_columns()
		
	def _get_current_playlist_menu(self):
		"""
		"""
		playlist = self.exaile.gui.main.get_selected_playlist()
	
		if playlist:
			return playlist.menu
	
		return None

	def _add_menu_item(self, menu):
		"""
			Add a new menu item to the current playlist menu
			This item will be used to display the tracks suggestions from
			musicbrainz database

			menu: the menu from the selected playlist
		"""
		menu.append_separator()
		self.menu_item = menu.append(_('Fill tags with MusicBrainz suggestions'))
		self.menu_item.connect('activate', self.show_tracks_suggestions, menu.playlist)
		self.menu_item.show()

	def show_tracks_suggestions(self, widget, playlist):
		"""
			Shows the window with tracks suggestions from Musicbrainz

			track: the selected track in current playlist, that will be
			used in the query
		"""
		self.selected_track = playlist.get_selected_track()
		print self.selected_track
		# while fetching the suggestions, we show a loading dialog
		self.loading_dialog.show()
		# use idle_add to show the track suggestions dialog only when
		# the webservice query returns
		# TODO: find a better way to handle this. Maybe using threads =D
		gobject.idle_add(self.dialog.present)
		
	def _fill_tracks_list(self, tracks_results):
		"""
			Fill the track suggestions list with the suggestions from
			the musicbrainz webservice

			tracks_results: the suggestions from the musicbrainz webservice
		"""
		self.loading_dialog.hide()
		store = self.tracks_list.get_model()
		for result in tracks_results:
			track = result.track
			store.append([
				result.score,
				track.artist.name,
				track.title,
				track.releases[0].title,
				self._get_album_type(track.releases[0].types),
				track.releases[0].tracksOffset + 1
			])

	def _clear_suggestions_list(self):
		"""
			Clear the tracks suggestions list
		"""
		store = self.tracks_list.get_model()
		store.clear()
		
	def _get_album_type(self, types_list):
		"""
			Gets the album type from a musicbrainz2.model.Release object
			The webservice sends the album type information in a URL 
			format like:
			http://musicbrainz.org/ns/mmd-1.0#Album

			We get the first type in the Release types list, and extract
			the type name, after de # symbol.

			types_list: the types list from de muscibrainz2.model.Release
			object
		"""
		if len(types_list) == 0:
			return None
		else:
			return re.search('#(\w+)', types_list[0]).group(1)
		
	def _add_list_columns(self):
		"""
			Add columns to the track suggestions list using the
			self.columns_titles and self.columns_widths properties
		"""
		self.tracks_list.set_model(model=gtk.ListStore(str, str, str, str, str, str))
		cell_renderer = gtk.CellRendererText()
		i = 0
		for title in self.columns_titles:
			column = gtk.TreeViewColumn(title, cell_renderer)
			column.set_min_width(self.columns_widths[i])
			column.set_max_width(self.columns_widths[i])
			self.tracks_list.append_column(column)
			column.add_attribute(cell_renderer, 'text', i)
			i += 1

	def on_btn_save_track_info_clicked(self, widget):
		"""
			Called when the Save button is clicked on the track
			suggestions dialog.
		"""
		model, iter = self.tracks_list.get_selection().get_selected()
		if iter is None:
			self._show_error_dialog(_(self.SELECT_TRACK_ERROR_MESSAGE))
		else:
			selected_suggestion = model.get(iter, 1, 2, 3, 5)
			self.write_tags_suggestions(selected_suggestion)

	def write_tags_suggestions(self, suggestion):
		"""
			Saves the data from the selected suggestion to the tags
			from the selected track in current playlist

			suggestion: the selected suggestion in the track suggestion
			list
		"""
		self.selected_track.set_tag('artist', [suggestion[0]])
		self.selected_track.set_tag('title', [suggestion[1]])
		self.selected_track.set_tag('album', [suggestion[2]])
		self.selected_track.set_tag('tracknumber', [suggestion[3]])
		self.selected_track.write_tags()
		self.clear_suggestions_list()
		self.dialog.hide()

	def _show_error_dialog(self, message):
		"""
			Shows an error message dialog

			message: the error message
		"""
		self.loading_dialog.hide()
		error_dialog = gtk.MessageDialog(self.exaile.gui.main.window, 0, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, message)
		error_dialog.connect('response', self.on_error_dialog_close)
		error_dialog.show()

	def on_error_dialog_close(self, widget, data=None):
		widget.hide()
		
	def on_dialog_close(self, widget, data=None):
		"""
			Called whe the tracks suggestions window is closed
		"""
		self._clear_suggestions_list()
		self.dialog.hide()
		return True

	def on_dialog_show(self, widget, data=None):
		"""
			Called when the tracks suggestions dialog is presented
			Actually, the window is presented only after the method ends
		"""
		try:
			tracks_results = self.track_search.get_tracks_suggestions(self.selected_track)
			self._fill_tracks_list(tracks_results)
		except WebServiceError:
			self._show_error_dialog(_(self.WS_ERROR_MESSAGE))

	def disable(self):
		"""
			Disable the plugin, destroying all the gui elements created
		"""
		self.dialog.destroy()
		self.loading_dialog.destroy()
		self.menu_item.destroy()
		
