/* The address of every name game.h declares (but the orig_ names, which the build makes), with the
   game's program taken to start at 0x60000000. The game is loaded elsewhere, but the menu reaches
   all of these counting from the pc, so what matters is only how far each is from the menu's code.
   The build adds this to the linker's script. */

/* names and text */
literal_string_vtable = 0x61585038;
pane_text_box = 0x609b2838;
text_box_write = 0x60e6e9f8;
text_counter_vtable = 0x616fd5e0;

/* layouts */
layout_memory = 0x61eb5cfc;
layout_find_button = 0x60e23224;
layout_find_pane = 0x60e23078;
layout_find_part = 0x60e230dc;
layout_pane_at = 0x60e2327c;
layout_animation = 0x60e23d04;
layout_animation_simple = 0x60e23d50;
layout_group_animation = 0x60e23c1c;

/* animations */
animation_set_frame = 0x60e2f6b8;
animation_rewind = 0x60e2f788;
animation_to_end = 0x60e2f7f8;
animation_last_frame = 0x60fc9fcc;

/* sounds and rumble */
sound_player = 0x61875ff4;
sound_names = 0x61875454;
sound_settings_init = 0x6085213c;
rumble_player = 0x61ea213c;
rumble_allowed = 0x6093bfb8;
rumble_find = 0x60d9d098;
rumble_make = 0x60d95b68;
rumble_play = 0x60d95da8;
rumble_end = 0x60d94228;

/* windows and the cursor */
window_input = 0x60e49b2c;
window_take_presses = 0x60e494c8;
window_press_handled = 0x60e4b580;
button_set_active = 0x60e313d8;
cursor_enable = 0x60e70f68;
cursor_activate = 0x60e70f28;
cursor_place = 0x60e72208;
current_place = 0x60e29fbc;
pointer_nowhere = 0x6150dff8;
cursor_move_to = 0x60e72264;
cursor_clear_links = 0x60e71ec0;
cursor_link_across = 0x60e71ad8;
cursor_link_up = 0x60e71750;
cursor_link_down = 0x60e71840;
cursor_link_left = 0x60e7153c;
cursor_set_links = 0x60e718b8;
cursor_add_pane = 0x60e711ac;
cursor_set_pane_group = 0x60e71480;
cursor_pane_reachable = 0x60e7130c;
cursor_pane_place = 0x60e71348;
cursor_set_pane_links = 0x60e71a04;

/* the pause window */
pause_redraw = 0x60be7e44;

/* the game's state: the Onion, the field, the day */
game_state = 0x61ea24bc;
onion_has = 0x60dfe7f4;
onion_stage_count = 0x60dfed98;
onion_stage_add = 0x60dfec0c;
onion_merged = 0x60dfe9d0;
is_ultra_spicy = 0x60dfe4e4;
is_pikmin_type = 0x60c921f8;
is_leader = 0x60c921e4;
game_hud = 0x618a1bd0;
day_clock = 0x61ea24dc;
clock_update_part = 0x60e0c604;

/* the Onion menu */
type_order = 0x614994f0;
type_place = 0x614994d0;
as_onion_button = 0x60bc0720;
onion_column_buttons = 0x60bc3c98;
onion_write_numbers = 0x60bc39b0;
onion_all_cannot = 0x60bc409c;

/* the system's file calls: the game's own entries for them, which jump on to the system's */
nn_fs_GetEntryType = 0x610ff290;
nn_fs_CreateFile = 0x610ff2a0;
nn_fs_OpenFile = 0x610fef00;
nn_fs_CloseFile = 0x610fef10;
nn_fs_GetFileSize = 0x610fef30;
nn_fs_ReadFile = 0x610fef40;
nn_fs_WriteFile = 0x610fef50;
nn_fs_SetFileSize = 0x610ff2b0;
