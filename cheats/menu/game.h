/* The game's functions and data the menu uses, under names of the menu's own.
 *
 * The game is not loaded at the addresses its program has: the system puts it elsewhere, and all
 * that stays the same is the distance from the mod's own program file to the game's code. So
 * nothing in the menu may hold an address of the game's, and every reference has to count from the
 * pc. Declared hidden (the pragma below is around all of them), every name here is reached that
 * way: the compiler makes each call and each load relative to the instruction, never through a
 * table of addresses. The address of each name is in game.ld.
 */
#pragma GCC visibility push(hidden)

/* the game's string of a name: its vtable, then its characters */
typedef struct { const void *vt; const char *s; } SafeString;
/* a text for a text box: its length, then its UTF-16 characters */
typedef struct { unsigned short length, pad; const unsigned short *chars; } Message;
/* a file the system has open */
typedef struct { void *handle; } FileHandle;

/* -- names and text -- */
extern const char literal_string_vtable[];                     /* the vtable of a string made from a literal, as every name looked up is */
extern void *pane_text_box(void *pane);                        /* the pane as a text box, or 0 */
extern void text_box_write(void *text_box, Message *text);     /* a text box's text set */
extern const char text_counter_vtable[];                       /* the vtable of a number's counter, which draws a number on screen */

/* -- layouts -- */
extern char *layout_memory;                                    /* at +0x18, the memory the layouts make what they need in */
extern void *layout_find_button(char *layout, SafeString *name);   /* a button of a layout, by name */
extern void *layout_find_pane(char *layout, SafeString *name);     /* a pane of a layout, by name */
extern char *layout_find_part(char *layout, SafeString *name);     /* a part's own layout, by its pane's name */
extern void *layout_pane_at(char *layout, void *point);            /* the pane of a layout under a point of the screen */
/* an animation of a layout, by name */
extern void *layout_animation(char *layout, void *memory, const char *name, int on);
/* the same, made as the Onion menu makes its own */
extern void *layout_animation_simple(char *layout, void *memory, const char *name, int on);
/* an animation of a layout, bound through one of its groups */
extern void *layout_group_animation(char *layout, void *memory, const char *name, const char *group, int on);

/* -- animations -- */
extern void animation_set_frame(float frame, void *animation);  /* an animation to a frame */
extern void animation_rewind(void *animation);                  /* an animation back to its start */
extern void animation_to_end(void *animation);                  /* an animation to its end */
extern unsigned short animation_last_frame(void *animation);    /* an animation's last frame */

/* -- sounds and rumble -- */
extern void *sound_player;                                      /* what plays the menus' sounds */
extern char *sound_names;                                       /* the table of the sounds' names: sound n's at +0x14 + 4n */
extern void sound_settings_init(void *sound);                   /* a sound's settings made ready */
extern void *rumble_player;                                     /* what plays the controllers' rumbles */
extern int rumble_allowed(void *rumbles);                       /* whether the controller is to rumble */
extern void *rumble_find(void *player, SafeString *name);       /* a rumble, by name */
extern void rumble_make(void *rumble, void *what);              /* a request to play that rumble, made in `rumble` */
extern void rumble_play(void *rumble, char *input);             /* the request played, on the controller of a window's input */
extern void rumble_end(void *rumble);                           /* the request done with */

/* -- windows and the cursor -- */
extern char *window_input(void *window);                        /* a window's input: the buttons held and pressed this frame */
extern void window_take_presses(void *window, int on);          /* a window's buttons taking presses, or not */
extern void window_press_handled(void *window);                 /* a window told that its press is being handled */
extern void button_set_active(void *button, int on);            /* a button on, or off */
extern void cursor_enable(void *cursor, int on);                /* the cursor on, or off (as a window changes tab or handles a press) */
extern void cursor_activate(void *cursor, int on);              /* a flag of the cursor's own, set and cleared with that */
extern void *cursor_place(void *cursor, int *player, int zero); /* the cursor's place a player is on (its button at +0x60) */
extern void *current_place(char *pointer, void *at);            /* the cursor's place now, from the input's pointer state */
extern const float pointer_nowhere[2];                          /* where the pointer is taken to be when it is not on the screen */
extern void cursor_move_to(void *cursor, void *button, int now);    /* the cursor to a button */
extern void cursor_clear_links(void *cursor, int *how);             /* every link of every button cleared */
extern void cursor_link_across(void *cursor, void *left, void *right);  /* two buttons left and right of each other */
/* up from `from` goes to `to` */
extern void cursor_link_up(void *cursor, void *from, int kind, int zero, void *to, int zero2);
/* down from `from` goes to `to` */
extern void cursor_link_down(void *cursor, void *from, int kind, int zero, void *to, int zero2);
/* left from a button goes to a pane's place */
extern void cursor_link_left(void *cursor, void *button, int kind, int zero, void *pane, int zero2);
/* a button's four links */
extern void cursor_set_links(void *cursor, void *button, int *left, int *up, int *right, int *down);
extern void cursor_add_pane(void *cursor, void *pane);              /* a pane made a place of the cursor's */
extern void cursor_set_pane_group(void *cursor, void *pane, int group);  /* the group a pane's place is in */
extern void cursor_pane_reachable(void *cursor, void *pane, int on);     /* a pane's place reachable, or not */
extern void *cursor_pane_place(void *cursor, void *pane);           /* a pane's place */
/* a pane's four links */
extern void cursor_set_pane_links(void *cursor, void *pane, int *left, int *up, int *right, int *down);

/* -- the pause window -- */
extern void pause_redraw(void *window);                         /* the page drawn again for its tab (menu_redraw runs after it) */

/* -- the game's state: the Onion, the field, the day -- */
extern char *game_state;                                        /* the game's state: among it the Onion's counts of each type and stage */
extern int onion_has(char *state, unsigned type);               /* whether the Onion holds a type (0 or 1) */
/* how many of a type and stage (leaf, bud, flower) the Onion holds */
extern int onion_stage_count(char *state, unsigned type, unsigned stage);
/* added to that, as the Onion's own code adds to it */
extern int onion_stage_add(char *state, unsigned type, unsigned stage, int add);
extern int onion_merged(char *state, unsigned type);            /* whether a type's Onion has merged into the one Onion */
extern int is_ultra_spicy(char *state);                         /* whether the game is on Ultra-Spicy: the field holds 60 Pikmin, not 100 */
extern int is_pikmin_type(int type);                            /* whether a number is a type of Pikmin (1 to 7) */
extern int is_leader(int player);                               /* whether a number is a leader's (8 to 12) */
extern char *game_hud;                                          /* the HUD: what shows the spray count; at +0x48 the Onion menu's variables */
extern char *day_clock;                                         /* the day's clock */
extern void clock_update_part(char *clock);                     /* its part of the day worked out again from how much of the day has gone */

/* -- the Onion menu -- */
extern const int type_order[7];                                 /* the order it lists types in: 3, 7, 5, 6, 2, 1, 4 */
extern const int type_place[7];                                 /* a type's place in that order, by type - 1 */
extern void *as_onion_button(void *button);                     /* the button, if of the menu's own kind (a flag at +0x7c), or 0 */
extern void onion_column_buttons(void *menu, unsigned column);  /* a column's buttons on or off by what can move */
extern void onion_write_numbers(void *menu);                    /* the columns' numbers written (menu_onion_numbers runs after it) */
extern int onion_all_cannot(void *menu, int add);               /* why "all" cannot change by `add`, or 0 if it can */

/* -- the system's file calls (nn::fs), through the game's own entries for them -- */
extern int nn_fs_GetEntryType(int *kind, const char *path);     /* what is at a path: 1 a file */
extern int nn_fs_CreateFile(const char *path, long long size);  /* a file made */
extern int nn_fs_OpenFile(FileHandle *handle, const char *path, int mode);   /* a file opened: mode 1 to read, 2 to write */
extern void nn_fs_CloseFile(FileHandle handle);                 /* a file closed */
extern int nn_fs_GetFileSize(long long *size, FileHandle handle);   /* a file's size */
/* a file read from */
extern int nn_fs_ReadFile(unsigned *read, FileHandle handle, long long offset, void *buffer, unsigned size);
/* a file written to (with option 1, flushed) */
extern int nn_fs_WriteFile(FileHandle handle, long long offset, const void *buffer, unsigned size, const int *option);
extern int nn_fs_SetFileSize(FileHandle handle, long long size);    /* a file's size set */

/* -- the game's own code of each function the menu runs instead of it: the build's stubs run the
      function's first word, which the patch replaced with a branch to the menu, then the rest -- */
extern void orig_links(void *window);                           /* the pause window's links of the cursor */
extern void orig_frame(void *window);                           /* each frame of the settings page */
extern int orig_spray_add(char *state, int add, unsigned player);   /* the spray count changed (kept 0 to 99), and returned */
extern int orig_spray_get(char *state, unsigned player);            /* the spray count */
extern void orig_onion_frame(void *menu);                       /* each frame of the Onion menu */
extern int orig_onion_change(void *menu, unsigned column, int add, int quiet);   /* a column's count changed */
extern int orig_onion_left(void *menu, int listed);             /* the "all" total of Pikmin left in the Onion */
extern int orig_onion_out(void *menu, int listed);              /* the "all" total of Pikmin in the squad */
extern void orig_onion_all(void *menu, int on);                 /* Select All on or off */
extern void orig_onion_arrows(void *menu);                      /* the columns' arrows' loops started and stopped */
#pragma GCC visibility pop
