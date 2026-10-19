/* The Cheats menu: a fourth tab, "Cheats", in the pause menu's Other Settings, and columns for
 * Purple and White Pikmin in the Onion menu.
 *
 * This is the menu's code. The build compiles it into the mod's own program file, and the patch
 * the build writes points some of the game's functions at the menu_<name> functions here: each
 * runs after the game's function, before it, or instead of it (one that runs instead reaches the
 * game's own code through orig_<name>, declared in game.h). The tab's rows come from rows.h, which
 * the build writes. Every row is one of them, and its value is a byte of `cheat_values`: the cheats'
 * switches, which the build also writes, read that byte each time the game runs one of the words
 * they stand in for, and run the game's own word or the cheat's.
 *
 * How the tab works, in the game's own terms. The window's tab number is 0 to 2 for its own tabs
 * and 3 for this one; the bubbles stand Radar, Gyro, Cheats, More. The window finds its own 30
 * buttons by name in one list, and a name it does not have counts as the list's place 0. This
 * tab's buttons are not in it, so whatever the game does with a button's place this code does for
 * them by name: what a press changes, which button looks chosen, where the cursor goes, what B
 * does. A row of panes has as many buttons as the widest row, in columns (Pa_DBtn_rc: row of
 * panes r, column c), and shows the list's row `first` + r: its name, its buttons' names, and
 * only the columns it has buttons for. A switch row has a button for each value: a press turns
 * the row to that value, and a press of the lit one turns the row off, so while it is off none
 * looks chosen. An action row's buttons each add Pikmin to the Onion, its name showing how many
 * of the type the Onion holds. A toggle row's buttons are its value, then buttons that each do
 * something once (set the day's clock).
 *
 * The list scrolls: the page has VISIBLE rows of panes (the game's window holds four) and the
 * list has ROWS. The cursor's links stop at the top and bottom rows of panes; up on the top one or
 * down on the bottom one, pressed or held, moves the list a row under the cursor instead, as the
 * game's own lists move theirs (by the same two bits of the input, with that way's arrow of the
 * scroll bar played). The list stays where the cursor was last (the place, kept in cheats.sav):
 * after B, on another tab, and when the window is made again, and the way down from the bubble
 * leads back to that button.
 *
 * The Onion menu's columns 6 and 7 are at the end of this file.
 */
#include "rows.h"
#include "game.h"

/* -- the pause window's fields -- */
#define AT(w, off, type) (*(type *)((char *)(w) + (off)))
#define LAYOUT(w)       ((char *)(w) + 0x180)                   /* its layout */
#define CURSOR(w)       AT(w, 0x238, void *)                    /* its cursor */
#define PLAYER(w)       AT(w, 0x458, int)                       /* the player it is open for */
#define READY(w)        AT(w, 0x460, unsigned char)             /* the page steps between tabs only while this is set */
#define ANIM(w, k)      AT(w, 0x464 + 4 * (k), void *)          /* its animations */
#define BUTTON(w, k)    AT(w, 0x49c + 4 * (k), void *)          /* its 30 buttons, by place */
#define PAGE(w)         AT(w, 0x540, int)                       /* the page open */
#define TAB(w)          AT(w, 0x544, int)                       /* the tab shown */
#define PLACE(w)        AT(w, 0x54c, int)                       /* its place: the tab's bubble, where the links put the cursor */
#define NEXT(w)         AT(w, 0x554, int)                       /* the button the cursor goes to after a press */
#define MOVE_PENDING(w) AT(w, 0x558, unsigned char)             /* and that it goes there next frame */
#define LOCK(w)         AT(w, 0x560, unsigned char)             /* the page locked as the tab changes: its buttons and the cursor off */
#define LOCK_FRAMES(w)  AT(w, 0x564, int)                       /* the frames until it unlocks */
#define BACK(w)         AT(w, 0x579, unsigned char)             /* the cursor went back to a bubble with B (a sound of its own) */
#define SETTING_CHANGE  8           /* the animations: which group of rows shows (its frame is the tab) */
#define SELECTION_ACTIVE 9          /* frame 0 the rows dimmed, 1 lit */
#define RADAR_BUBBLE 8              /* the window's buttons 8, 9 and 10 are its bubbles */
#define GYRO_BUBBLE 9
#define MORE_BUBBLE 10
#define SETTINGS 1                  /* the window's page: 0 its top menu, 1 Other Settings */
#define GYRO 1                      /* the tabs: 0 Radar, 1 Gyro, 2 More, and 3 this one */
#define MORE 2
#define CHEATS 3
#define OUR_PLACE 0x20              /* the place for the Cheats bubble: none of the window's 30 buttons */
#define OUR_NEXT 0x21               /* NEXT for the button this code chose (`pending`): none of the 30 either */
#define SOUND_MOVE 0x352            /* the sounds: the cursor's move between buttons, */
#define SOUND_BACK 0x358            /* and its move back to a bubble with B */
/* the input (window_input): +8 what was pressed this frame, +0x18 what the game's lists also move
   by while a direction is held. Up and down are two bits each, the D-pad's and the stick's. */
#define INPUT_PRESSED(i) AT(i, 8, unsigned)
#define INPUT_HELD(i)    AT(i, 0x18, unsigned)
#define UP   0x11000
#define DOWN 0x22000
#define REPEAT 8                    /* frames between moves of a held direction, as the cursor's own */

/* -- a pane of a layout, as the game's code uses one -- */
#define PANE_Y(p)       AT(p, 0x1c, float)      /* where it stands in its parent: +0x18 x, +0x1c y */
#define PANE_H(p)       AT(p, 0x3c, float)      /* its size: +0x38 width, +0x3c height */
#define PANE_FLAGS(p)   AT(p, 0x40, unsigned char)
#define SHOWN 0x01                  /* shown (and a hidden button is out of the cursor's reach) */
#define MOVED 0x10                  /* its matrix to be worked out again: set by the game after it moves or sizes a pane */

unsigned char cheat_values[SLOTS];          /* by slot: 0 off, n the row's n-th value; the switches read these */
/* and, in three slots no row has, where the cursor was last on this tab: saved with the rows'
   values, so that the tab opens there again */
#define PLACE_FIRST  cheat_values[PLACE_SLOT]       /* the list's row in the top row of panes */
#define PLACE_ROW    cheat_values[PLACE_SLOT + 1]   /* the list's row the cursor was on */
#define PLACE_COLUMN cheat_values[PLACE_SLOT + 2]   /* and its column */

static void *window;                        /* the window these were found in */
static void *bubble;                        /* Pa_MenuBtn_03, the tab's bubble */
static void *buttons[VISIBLE][COLUMNS];     /* Pa_DBtn_rc: the row of panes r's, its first value's at column 0 */
static void *panes[VISIBLE][COLUMNS];       /* the same buttons' panes, hidden where the row has no button */
static void *names[VISIBLE][COLUMNS];       /* their text boxes (the values' names, a toggle row's actions', or an action row's amounts) */
static void *labels[VISIBLE];               /* T_DItem_0r: each row's name */
static unsigned short label_text[VISIBLE][MAX_LABEL + 1];  /* an action row's name as shown: with the Onion's count */
static int first;                           /* the row of the list in the top row of panes */
static void *thumb;                         /* the scroll bar's thumb (W_Thumb_00), or 0 */
static void *arrow_move[2];                 /* its arrows' ArrowMove: 0 up, 1 down */
static void *pending;                       /* where the cursor goes when the window next moves it for a press */
static void *last_focus;                    /* the button of this tab's the cursor was on last frame, or 0 */
static int since;                           /* frames since the cursor moved or the list did */
static unsigned char relink;                /* the top row's link up to the bubble, still to be made (next frame) */
static unsigned char dirty;                 /* a row's value changed since cheats.sav was last written */
static unsigned char moved;                 /* the place changed since then */

static const char PATH[] = "save:/cheats.sav";      /* the menu's own file, in the game's save beside its files */

static int length(const unsigned short *s)
{
    int n = 0;
    while (s[n])
        n++;
    return n;
}

static void make_room(void *text_box, int n)
{
    /* as the game makes room before it sets a button's text; once, at setup, for the longest text
       the box will show (a text box keeps what fits of a longer one, so no text after needs more) */
    if (text_box)
        ((void (*)(void *, void *, int))(*(void ***)text_box)[0x70 / 4])(text_box, *(void **)(layout_memory + 0x18), n);
}

static void put_text(void *text_box, const unsigned short *s)
{
    Message m;
    if (!text_box)
        return;
    m.length = length(s);
    m.pad = 0;
    m.chars = s;
    text_box_write(text_box, &m);
}

static void set_text(void *text_box, const unsigned short *s)
{
    make_room(text_box, length(s));
    put_text(text_box, s);
}

static void name_of(char *out, const char *stem, int n)    /* stem then two digits: "Pa_DBtn_" 13 -> "Pa_DBtn_13" */
{
    while (*stem)
        *out++ = *stem++;
    *out++ = '0' + n / 10;
    *out++ = '0' + n % 10;
    *out = 0;
}

static void *find_button(void *w, const char *name)
{
    SafeString s;
    s.vt = literal_string_vtable;
    s.s = name;
    return layout_find_button(LAYOUT(w), &s);
}

static void *find_pane(char *layout, const char *name)
{
    SafeString s;
    if (!layout)
        return 0;
    s.vt = literal_string_vtable;
    s.s = name;
    return layout_find_pane(layout, &s);
}

static char *find_part(char *layout, const char *name)
{
    SafeString s;
    if (!layout)
        return 0;
    s.vt = literal_string_vtable;
    s.s = name;
    return layout_find_part(layout, &s);
}

static void *find_text(char *layout, const char *name)
{
    void *pane = find_pane(layout, name);
    return pane ? pane_text_box(pane) : 0;
}

static void *part_text(void *w, const char *part)               /* the T_Btn_00 of a button part */
{
    return find_text(find_part(LAYOUT(w), part), "T_Btn_00");
}

static void show_pane(void *pane, int on)
{
    if (pane)
        PANE_FLAGS(pane) = on ? PANE_FLAGS(pane) | SHOWN : PANE_FLAGS(pane) & ~SHOWN;
}

static int ours(void *w)                                        /* the window this tab was set up in */
{
    return w == window && bubble;
}

static int values_of(int row)                                   /* the list's row's buttons: its values (and actions), or amounts */
{
    return ROW_COLUMNS[row];
}

static int shown(int r)                                         /* the columns the row of panes r shows */
{
    return values_of(first + r);
}

static void *ours_named(const char *s)                          /* this tab's button of that name, or 0 */
{
    const char *t = "Pa_MenuBtn_03";
    int k, r, c;
    if (!s)
        return 0;
    if (s[0] == 'P' && s[1] == 'a' && s[2] == '_' && s[3] == 'D' && s[4] == 'B' && s[5] == 't' && s[6] == 'n' && s[7] == '_' &&
        s[8] >= '0' && s[8] <= '9' && s[9] >= '0' && s[9] <= '9' && !s[10]) {
        r = s[8] - '0';
        c = s[9] - '0';
        return r < VISIBLE && c < COLUMNS ? buttons[r][c] : 0;
    }
    for (k = 0; t[k] && s[k] == t[k]; k++)
        ;
    return t[k] || s[k] ? 0 : bubble;
}

static const char *name_in(SafeString *s)                       /* what the game does to a name before it reads it */
{
    ((void (*)(SafeString *))((void **)s->vt)[0x0c / 4])(s);
    return s->s;
}

static void *focused(void *w)                                   /* this tab's button the cursor is on, or 0 */
{
    /* The cursor gives its place, not the button: the game asks the place for its button's name
       (the place's first virtual call: the button at +0x60, its name at +0x58), and so does this. */
    int player = PLAYER(w) != 0;
    void *place = cursor_place(CURSOR(w), &player, 0);
    SafeString s;
    if (!place)
        return 0;
    s.vt = 0;
    s.s = 0;
    ((void (*)(SafeString *, void *))(*(void ***)place)[0])(&s, place);
    return s.vt ? ours_named(name_in(&s)) : 0;
}

static int row_of(void *b, int *column)                         /* the row of panes a button of this tab's is in, or -1 */
{
    int r, c;
    if (!b)
        return -1;
    for (r = 0; r < VISIBLE; r++)
        for (c = 0; c < COLUMNS; c++)
            if (buttons[r][c] == b) {
                if (column)
                    *column = c;
                return r;
            }
    return -1;
}

static void chosen(void *button, int on)                        /* the "chosen" look, as the game sets its own */
{
    if (button)
        *(float *)(*(char **)((char *)button + 0x30) + 0x10) = on ? 1.0f : 0.0f;
}

static int value(int row)                                       /* a switch row's value; an action row has none (0) */
{
    return ROW_SLOT[row] < SLOTS ? cheat_values[ROW_SLOT[row]] : 0;
}

static int lit(int row)                                         /* the column of the row that looks chosen, or -1 */
{
    return value(row) - 1;                                      /* value n's is column n - 1: none while off, nor on an action row */
}

static int rest(int row)                                        /* the column the cursor comes to the row on */
{
    return lit(row) < 0 ? 0 : lit(row);
}

/* -- the place: where the cursor was last on this tab -- */

static int place_first(void)                                    /* the list's first row on the page there, as far as the list goes */
{
    return PLACE_FIRST > ROWS - VISIBLE ? ROWS - VISIBLE : PLACE_FIRST;
}

static void *place_button(void)                                 /* the button there, on the page as it is (or the nearest it has) */
{
    int r = PLACE_ROW - first, c = PLACE_COLUMN;
    r = r < 0 ? 0 : r >= VISIBLE ? VISIBLE - 1 : r;
    return buttons[r][c < shown(r) ? c : shown(r) - 1];
}

static void remember(void *w, int r, int c)                     /* the cursor on the row of panes r, column c */
{
    if (PLACE_FIRST == first && PLACE_ROW == first + r && PLACE_COLUMN == c)
        return;
    PLACE_FIRST = first;
    PLACE_ROW = first + r;
    PLACE_COLUMN = c;
    moved = 1;                                                  /* written to cheats.sav with the rows' values */
    cursor_link_down(CURSOR(w), bubble, 2, 0, place_button(), 0);   /* the bubble's way down: here */
}

/* -- the Onion's Pikmin (an action row), by the game's own functions -- */

static int in_onion(int type)                                   /* the Onion holds the type (it could give them out) */
{
    return game_state && onion_has(game_state, type) != 0;
}

static int onion_count(int type)                                /* all its stages, as the Onion menu counts them */
{
    return onion_stage_count(game_state, type, 0) + onion_stage_count(game_state, type, 1) + onion_stage_count(game_state, type, 2);
}

static void add_pikmin(int type, int n)
{
    int have;
    if (!in_onion(type))
        return;                                                 /* none of the type in the Onion: it could not give them out */
    have = onion_count(type);
    if (n > ONION_MOST - have)
        n = ONION_MOST - have;                                  /* past it, the game's own setter makes them all flowers */
    if (n > 0)
        onion_stage_add(game_state, type, FLOWER, n);           /* the count the Onion's own code adds to: saved with the day */
}

/* -- the day's clock (a toggle row's actions: the Day Timer's Set start and Set noon) -- */

#define CLOCK_GONE(c)       AT(c, 0x44, float)                  /* how much of the day has gone: 0 its start, 0.5 noon, 1 its end */
#define CLOCK_MINUTES(c)    AT(c, 0xe4, float)                  /* the day's length in minutes (13 in story mode) */
#define CLOCK_EVENTS 9                                          /* timed events: the sunset warnings, the juice warnings */
#define EVENT_MINUTES(c, k) AT(c, 0x58 + 0x10 * (k), int)       /* each at a time left (its minutes and seconds), once */
#define EVENT_SECONDS(c, k) AT(c, 0x5c + 0x10 * (k), int)
#define EVENT_DONE(c, k)    AT(c, 0x60 + 0x10 * (k), unsigned char)   /* and whether it has come */
#define DAY_START_AT 0.0f                                       /* where the game's own day begins */
#define NOON_AT 0.5f                                            /* noon, where the game's own code tells the day's halves apart */

static void set_time(float gone)
{
    char *clock = day_clock;
    float left;
    int minutes, seconds, k;
    if (!clock)
        return;
    /* as the game's own code sets the time (as a map starts, by an event script's command, at the
       day's end): how much of the day has gone, then the part of the day worked out again */
    CLOCK_GONE(clock) = gone;
    clock_update_part(clock);
    /* and every event still to come comes again: the game fires one, once, when the time left is no
       more than its own, the minutes and then the seconds worked out as here */
    left = (1.0f - gone) * CLOCK_MINUTES(clock);
    minutes = (int)left;
    seconds = (int)((left - (float)minutes) * 60.0f);
    for (k = 0; k < CLOCK_EVENTS; k++)
        if (minutes > EVENT_MINUTES(clock, k) || (minutes == EVENT_MINUTES(clock, k) && seconds > EVENT_SECONDS(clock, k)))
            EVENT_DONE(clock, k) = 0;
}

static void act(int what)                                       /* a toggle row's button after its value, pressed */
{
    if (what == ACTION_DAY_START)
        set_time(DAY_START_AT);
    else if (what == ACTION_DAY_NOON)
        set_time(NOON_AT);
}

static const unsigned short *label_of(int r)                   /* the name of the list's row in the row of panes r */
{
    int row = first + r, n = 0, k = 0, count;
    unsigned char digits[8];
    unsigned short *out = label_text[r];
    const unsigned short *s;
    if (!ROW_PIKMIN[row])
        return TEXT + ROW_LABEL[row];
    for (s = TEXT + ROW_LABEL[row]; *s; s++)
        out[n++] = *s;
    if (!in_onion(ROW_PIKMIN[row])) {
        for (s = TEXT + NOT_FOUND; *s; s++)
            out[n++] = *s;
    } else {
        for (s = TEXT + COUNT_AFTER; *s; s++)
            out[n++] = *s;
        count = onion_count(ROW_PIKMIN[row]);
        count = count > SHOWN_MOST ? SHOWN_MOST : count < SHOWN_LEAST ? SHOWN_LEAST : count;
        if (count < 0) {
            out[n++] = '-';
            count = -count;
        }
        do {
            digits[k++] = count % 10;
            count /= 10;
        } while (count);
        while (k)
            out[n++] = '0' + digits[--k];
    }
    out[n] = 0;
    return out;
}

static void cursor_sound(void *w, int back)                    /* what the page does as the cursor reaches a button: a sound and a rumble */
{
    unsigned sound[0x40 / 4];
    SafeString s;
    unsigned rumble[0x40 / 4];
    void *player = sound_player;
    sound_settings_init(sound);
    ((void (*)(void *, void *, void *))(*(void ***)player)[3])(player, *(void **)(sound_names + 0x14 + 4 * (back ? SOUND_BACK : SOUND_MOVE)), sound);
    if (rumble_allowed(AT(w, 0xb8, void *))) {
        s.vt = literal_string_vtable;
        s.s = "point_target_rumble";
        rumble_make(rumble, rumble_find(rumble_player, &s));
        rumble_play(rumble, window_input(w));
        rumble_end(rumble);
    }
}

static void show_tab(void *w, int tab)                         /* a tab shown, as the page's own switch shows one */
{
    TAB(w) = tab;
    LOCK(w) = 1;
    LOCK_FRAMES(w) = 1;
    window_take_presses(w, 0);
    cursor_enable(CURSOR(w), 0);
    cursor_activate(CURSOR(w), 0);
    if (ANIM(w, SETTING_CHANGE))
        animation_set_frame((float)tab, ANIM(w, SETTING_CHANGE));
    pause_redraw(w);
}

/* -- the list on the page -- */

static void looks(void *w)                                     /* which button of each row looks chosen (on this tab) */
{
    int r, c;
    if (PAGE(w) != SETTINGS || TAB(w) != CHEATS)
        return;
    for (r = 0; r < VISIBLE; r++)
        for (c = 0; c < COLUMNS; c++)
            chosen(buttons[r][c], c < shown(r) && lit(first + r) == c);
}

static void counts(void)                                        /* the names of the rows shown (an action row's count) */
{
    int r;
    for (r = 0; r < VISIBLE; r++)
        put_text(labels[r], label_of(r));
}

static void refresh(void *w)                                   /* the rows of panes showing the list from `first` */
{
    int r, c;
    counts();
    for (r = 0; r < VISIBLE; r++)
        for (c = 0; c < COLUMNS; c++) {
            if (c < shown(r))
                put_text(names[r][c], TEXT + ROW_NAME[first + r][c]);
            show_pane(panes[r][c], c < shown(r));
        }
    if (thumb) {
        PANE_Y(thumb) = THUMB_TOP - first * THUMB_STEP;
        PANE_FLAGS(thumb) |= MOVED;
    }
    looks(w);
}

static void link_tab(void *w, int up_to_bubble)                /* the cursor's links of this tab, for the rows shown now */
{
    void *cursor = CURSOR(w);
    int how[4] = {5, 0, 0, 0};
    int r, c, n, m;
    cursor_clear_links(cursor, how);
    cursor_link_across(cursor, BUTTON(w, RADAR_BUBBLE), BUTTON(w, GYRO_BUBBLE));
    cursor_link_across(cursor, BUTTON(w, GYRO_BUBBLE), bubble);
    cursor_link_across(cursor, bubble, BUTTON(w, MORE_BUBBLE));
    cursor_link_down(cursor, bubble, 2, 0, place_button(), 0);  /* as More's: down to the page, where the cursor was last, */
    if (up_to_bubble)                                           /* and up from the top row, at the list's top */
        for (c = 0; c < shown(0); c++)
            cursor_link_up(cursor, buttons[0][c], 2, 0, bubble, 0);
    for (r = 0; r < VISIBLE; r++)
        for (c = 0; c + 1 < shown(r); c++)
            cursor_link_across(cursor, buttons[r][c], buttons[r][c + 1]);
    for (r = 0; r + 1 < VISIBLE; r++) {                         /* up and down to the same column, or the nearest a shorter row has */
        n = shown(r);
        m = shown(r + 1);
        for (c = 0; c < n; c++)
            cursor_link_down(cursor, buttons[r][c], 2, 0, buttons[r + 1][c < m ? c : m - 1], 0);
        for (c = 0; c < m; c++)
            cursor_link_up(cursor, buttons[r + 1][c], 2, 0, buttons[r][c < n ? c : n - 1], 0);
    }
    /* nothing below the bottom row, nothing above the top one but at the list's top: those presses
       move the list (menu_frame), and a column a row does not show is linked from nowhere */
}

static void play(void *animation)                              /* an animation from its start (the animator's virtual call +0x58) */
{
    if (animation)
        ((void (*)(void *, float))(*(void ***)animation)[0x58 / 4])(animation, 1.0f);
}

static void *scroll(void *w, int step, int r, int c)           /* the list a row on; the cursor stays on its row of panes */
{
    void *to;
    first += step;
    refresh(w);
    link_tab(w, 0);                                             /* the top row's link up: next frame, so this press cannot use it */
    relink = first == 0;
    to = buttons[r][c < shown(r) ? c : shown(r) - 1];
    if (to != buttons[r][c])
        cursor_move_to(CURSOR(w), to, 1);                       /* the nearest column the row now shown has */
    cursor_sound(w, 0);                                         /* the cursor did not move: the move's sound, as the game's lists play */
    play(arrow_move[step > 0]);
    return to;
}

static void scroll_bar(void *w)                                 /* the game's scroll bar, sized for the list (or hidden) */
{
    char *part = find_part(LAYOUT(w), "Pa_ScrollBar_00");
    void *p;
    if (!part)
        return;
    if (!SCROLLS) {                                             /* a list the page holds: no bar */
        show_pane(find_pane(LAYOUT(w), "Pa_ScrollBar_00"), 0);
        return;
    }
    p = find_pane(part, "W_ScrollBox_00");                      /* the track, from the first row to the last */
    if (p) {
        PANE_H(p) = TRACK_H;
        PANE_FLAGS(p) |= MOVED;
    }
    thumb = find_pane(part, "W_Thumb_00");                      /* the thumb: the share of the list on the page */
    if (thumb)
        PANE_H(thumb) = THUMB_H;
    p = find_pane(part, "Pa_Arrow_00");                         /* the arrows, past each end of the track */
    if (p) {
        PANE_Y(p) = ARROW_UP_Y;
        PANE_FLAGS(p) |= MOVED;
    }
    p = find_pane(part, "Pa_Arrow_01");
    if (p) {
        PANE_Y(p) = ARROW_DOWN_Y;
        PANE_FLAGS(p) |= MOVED;
    }
    /* their animation as a move plays it, made as the game's own lists make theirs */
    p = find_part(part, "Pa_Arrow_00");
    arrow_move[0] = p ? layout_animation(p, *(void **)(layout_memory + 0x18), "ArrowMove", 1) : 0;
    p = find_part(part, "Pa_Arrow_01");
    arrow_move[1] = p ? layout_animation(p, *(void **)(layout_memory + 0x18), "ArrowMove", 1) : 0;
}

/* -- after the pause window's setup: this tab's buttons and texts found by name -- */
void menu_setup(void *w)
{
    char name[16];
    int r, c;
    window = w;
    bubble = 0;
    pending = 0;
    last_focus = 0;
    first = place_first();                                      /* the list where the cursor was last (cheats.sav, read at boot) */
    since = 0;
    relink = 0;
    thumb = 0;
    arrow_move[0] = arrow_move[1] = 0;
    for (r = 0; r < VISIBLE; r++)
        for (c = 0; c < COLUMNS; c++) {
            name_of(name, "Pa_DBtn_", 10 * r + c);
            buttons[r][c] = find_button(w, name);
            if (!buttons[r][c])
                return;                                         /* not the mod's layout: the tab stays out of the way */
            panes[r][c] = find_pane(LAYOUT(w), name);
            names[r][c] = part_text(w, name);                   /* every column's: the code writes each button's name */
        }
    bubble = find_button(w, "Pa_MenuBtn_03");
    if (!bubble)
        return;
    /* what the setup does to its own buttons 8 to 28, the bubbles and the rows: two flags cleared */
    *(unsigned *)((char *)bubble + 8) &= ~3u;
    for (r = 0; r < VISIBLE; r++)
        for (c = 0; c < COLUMNS; c++)
            *(unsigned *)((char *)buttons[r][c] + 8) &= ~3u;
    for (r = 0; r < VISIBLE; r++) {
        name_of(name, "T_DItem_", r);
        labels[r] = find_text(LAYOUT(w), name);
        make_room(labels[r], MAX_LABEL);
        for (c = 0; c < COLUMNS; c++)
            make_room(names[r][c], MAX_NAME);
    }
    set_text(part_text(w, "Pa_MenuBtn_03"), TEXT + TAB_LABEL);
    scroll_bar(w);
    refresh(w);
}

/* -- after the page is drawn again for its tab: which button of this tab looks chosen -- */
void menu_redraw(void *w)
{
    int r, c, mine;
    if (!ours(w))
        return;
    mine = PAGE(w) == SETTINGS && TAB(w) == CHEATS;
    /* the game's redraw begins with this call on each of its buttons; on this tab's, here */
    ((void (*)(void *))(*(void ***)bubble)[0x18 / 4])(bubble);
    for (r = 0; r < VISIBLE; r++)
        for (c = 0; c < COLUMNS; c++)
            ((void (*)(void *))(*(void ***)buttons[r][c])[0x18 / 4])(buttons[r][c]);
    chosen(bubble, mine);
    if (!mine)
        return;
    chosen(BUTTON(w, RADAR_BUBBLE), 0);                         /* the game's redraw has no case for tab 3: nothing set these */
    chosen(BUTTON(w, GYRO_BUBBLE), 0);
    chosen(BUTTON(w, MORE_BUBBLE), 0);
    looks(w);
    counts();                                                   /* the Onion's counts as they are now (the day goes on between pauses) */
}

/* -- before the pause window handles a press: this tab's buttons are handled here, whole -- */
int menu_press(void *w, SafeString *pressed)
{
    void *button;
    int r, c = 0;
    if (!ours(w) || PAGE(w) != SETTINGS)
        return 0;
    button = ours_named(name_in(pressed));
    if (!button)
        return 0;
    /* as for the game's own rows: */
    window_press_handled(w);
    window_take_presses(w, 1);
    cursor_enable(CURSOR(w), 1);
    READY(w) = 1;
    r = row_of(button, &c);
    if (r < 0) {
        pending = place_button();                               /* the bubble: down to the page, where the cursor was last */
    } else if (c >= shown(r)) {
        pending = buttons[r][rest(first + r)];                  /* a column hidden for this row (out of the cursor's reach): nothing */
    } else if (ROW_PIKMIN[first + r]) {
        add_pikmin(ROW_PIKMIN[first + r], ROW_AMOUNT[first + r][c]);   /* an action row: its amount, once (nothing to keep) */
        counts();                                               /* its name shows the new count at once */
        pending = button;
    } else if (c >= ROW_VALUES[first + r]) {
        act(ROW_ACTION[first + r][c]);                          /* a toggle row's button after its value: once (nothing to keep) */
        pending = button;
    } else {
        /* column c: the row's (c + 1)-th value, or, pressed while it is the one lit, the row off */
        cheat_values[ROW_SLOT[first + r]] = value(first + r) == c + 1 ? 0 : c + 1;
        dirty = 1;                                              /* kept in cheats.sav */
        pending = button;                                       /* the cursor stays (the game's own rows move it on to the next row) */
    }
    MOVE_PENDING(w) = 1;                                        /* the cursor moves next frame, to `pending`; the links leave it be */
    NEXT(w) = OUR_NEXT;
    pause_redraw(w);
    return 1;
}

/* -- instead of the page's links of the cursor: the game's for its own tabs, this for Cheats -- */
void menu_links(void *w)
{
    void *cursor = CURSOR(w);
    if (!ours(w) || PAGE(w) != SETTINGS || TAB(w) != CHEATS) {
        orig_links(w);
        if (ours(w) && PAGE(w) == SETTINGS) {                   /* the Cheats bubble stands between Gyro's and More's now */
            cursor_link_across(cursor, BUTTON(w, GYRO_BUBBLE), bubble);
            cursor_link_across(cursor, bubble, BUTTON(w, MORE_BUBBLE));
        }
        return;
    }
    link_tab(w, first == 0);
    relink = 0;
    if (!MOVE_PENDING(w))
        cursor_move_to(cursor, PLACE(w) == OUR_PLACE ? bubble : BUTTON(w, (unsigned)PLACE(w) < 30 ? PLACE(w) : 0), 1);
}

/* -- instead of the settings page's frame: the game's, with this tab put among its own -- */
void menu_frame(void *w)
{
    char *input;
    void *now;
    unsigned pressed, held;
    int tab, was_locked, back, borrowed = 0, across = 0, r, c = 0, step;
    if (!ours(w) || PAGE(w) != SETTINGS) {
        orig_frame(w);
        return;
    }
    tab = TAB(w);
    was_locked = LOCK(w);
    back = BACK(w);                                             /* the game clears it as its frame ends */
    if (!was_locked) {
        if (MOVE_PENDING(w) && NEXT(w) == OUR_NEXT) {           /* a press of this tab's: the cursor where it chose */
            MOVE_PENDING(w) = 0;
            if (pending)
                cursor_move_to(CURSOR(w), pending, 1);          /* (the press's own sound comes from the layouts' command table) */
            pending = 0;
        }
        if (READY(w)) {
            input = window_input(w);
            if (*(int *)(input + 8) < 0) {                      /* the buttons that step between tabs: a step left */
                if (tab == CHEATS) {
                    TAB(w) = MORE;                              /* the game's own step from More, to Gyro */
                    borrowed = 1;
                } else if (tab == MORE)
                    across = 1;                                 /* its step from More lands on Cheats */
            } else if (input[0xb] & 0x40) {                     /* a step right */
                if (tab == CHEATS) {
                    TAB(w) = GYRO;                              /* the game's own step from Gyro, to More */
                    borrowed = 1;
                } else if (tab == GYRO)
                    across = 1;                                 /* its step from Gyro lands on Cheats */
            }
        }
    }
    orig_frame(w);
    if (borrowed && !LOCK(w))
        TAB(w) = CHEATS;                                        /* it did not step after all */
    if (across && LOCK(w) && TAB(w) != tab) {                   /* it stepped, sound and all: on to Cheats instead */
        TAB(w) = CHEATS;
        if (ANIM(w, SETTING_CHANGE))
            animation_set_frame((float)CHEATS, ANIM(w, SETTING_CHANGE));
        pause_redraw(w);
        PLACE(w) = OUR_PLACE;
    }
    now = focused(w);                                           /* this tab's button the cursor is on, or 0 */
    if (!was_locked && !LOCK(w)) {
        if (now == bubble && TAB(w) != CHEATS) {                /* the cursor on the bubble: its tab, as for the game's bubbles */
            show_tab(w, CHEATS);
            PLACE(w) = OUR_PLACE;
            cursor_sound(w, 0);
        } else if (now && now != last_focus)
            cursor_sound(w, back);                              /* the game sounds the cursor reaching its own buttons only */
        if (row_of(now, 0) >= 0 && ANIM(w, SELECTION_ACTIVE))
            animation_set_frame(1.0f, ANIM(w, SELECTION_ACTIVE));   /* the rows lit with the cursor on them (the game would dim them) */
    }
    if (TAB(w) != CHEATS) {                                     /* another tab: this one kept as it is, unseen */
        relink = 0;
    } else if (!was_locked && !LOCK(w)) {
        if (relink) {
            link_tab(w, first == 0);
            relink = 0;
        }
        r = row_of(now, &c);
        if (r >= 0 && now == last_focus && !MOVE_PENDING(w)) {  /* on a row since last frame: up at the top, down at the bottom */
            input = window_input(w);
            pressed = INPUT_PRESSED(input);
            held = pressed | INPUT_HELD(input);
            step = 0;
            if (r == VISIBLE - 1 && first + VISIBLE < ROWS && ((pressed & DOWN) || ((held & DOWN) && since >= REPEAT)))
                step = 1;
            else if (r == 0 && first > 0 && ((pressed & UP) || ((held & UP) && since >= REPEAT)))
                step = -1;
            if (step) {
                now = scroll(w, step, r, c);
                since = -1;
            }
        }
        r = row_of(now, &c);
        if (r >= 0)
            remember(w, r, c);                                  /* where the cursor is now, the list as it is now */
    }
    since = now != last_focus ? 0 : since < 0x7fff ? since + 1 : since;
    last_focus = now;
}

/* -- before the page handles B: from a row of this tab, back to its bubble -- */
int menu_back(void *w)
{
    if (!ours(w) || PAGE(w) != SETTINGS || LOCK(w) || row_of(focused(w), 0) < 0)
        return 0;
    cursor_move_to(CURSOR(w), bubble, 1);
    BACK(w) = 1;                                                /* the list kept as it is: the bubble's way down leads back here */
    return 1;
}

/* -- Infinite Spicy Spray, a row of the menu's own code: with less than one spray you are given
      one, and otherwise using one takes none from the count -- */

static int infinite_spray(void)
{
    return cheat_values[INFINITE_SPRAY_SLOT] != 0;
}

static void show_sprays(char *state, unsigned player, int n)
{
    /* What the HUD shows is not read from the count: the game's own code writes it there each time
       it changes the count (a spray used or given, berries' drops made into a spray). In Bingo
       Battle (mode 3) each player has a number of their own. */
    char *hud = game_hud, *shown;
    if (!hud)
        return;
    if (*(int *)(state + 0x2f0) == 3) {
        shown = *(char **)(hud + 0x5c + 4 * (player < 2 ? player : 0));
        if (shown)
            *(int *)(shown + 0xbd8) = n;
    } else {
        shown = *(char **)(hud + 0x58);
        if (shown)
            *(int *)(shown + 0x10e8) = n;
    }
}

/* -- instead of the game's change of the spray count: a spray used takes none while the row is on
      (the caller shows what this returns, the count as it is) -- */
int menu_spray_add(char *state, int add, unsigned player)
{
    if (add < 0 && infinite_spray())
        return orig_spray_get(state, player);
    return orig_spray_add(state, add, player);
}

/* -- instead of the game's read of the spray count: while the row is on, a count of none becomes
      one, for real and on the HUD, the first time anything asks (the HUD asks every frame) -- */
int menu_spray_get(char *state, unsigned player)
{
    int n = orig_spray_get(state, player);
    if (n < 1 && infinite_spray()) {
        n = orig_spray_add(state, 1 - n, player);
        if (n > 0)
            show_sprays(state, player, n);
    }
    return n;
}

/* -- carrying -- */

/* after the game works out a carried thing's speed: Pikmin Carry Speed's value on top of Pikmin No
   Carry Penalty's, so that with both rows on, Pikmin carry faster than they walk. No Carry
   Penalty's entry makes the speed the carriers' walking speed and goes round the constant Carry
   Speed's entries change (the 42 the speed is worked out from), so the two entries alone never
   add up */
float menu_carry_speed(void *carried, float speed)
{
    unsigned k = cheat_values[CARRY_SPEED_SLOT];
    if (cheat_values[NO_CARRY_PENALTY_SLOT] && k && k < sizeof CARRY_SPEED_BY / sizeof CARRY_SPEED_BY[0])
        speed *= CARRY_SPEED_BY[k];                             /* what the value's entry makes the 42, over 42 */
    return speed;
}

#define CARRIERS(c)          AT(c, 0x3b8, int)                  /* a carried thing's carry state: how many carry it, */
#define CARRIED_STRENGTH(c)  AT(c, 0x3b0, int)                  /* and their strength, as each added it */

/* before the game looks at a carried thing's carriers' strength (as one joins or lets go; while it
   is not 0, the number over the thing stays): none, with nobody carrying it. A carrier adds its
   strength as it joins and takes it away as it lets go, each by Pikmin Carry Strength's value of
   the moment, so a value changed in between (the game's own never changes) would leave a strength
   over a thing nobody carries */
int menu_carried(char *carry)
{
    if (CARRIERS(carry) == 0)
        CARRIED_STRENGTH(carry) = 0;
    return 0;                                                   /* and then the game's own */
}

/* -- cheats.sav: the rows' values and the place, in a file of the menu's own in the game's save -- */
#define HEADER 8                    /* "P3CM", the layout version, how many slots follow (two bytes each, low first) */

/* after the game reads its settings (setting.sav): the menu's, unless it holds changes not yet written */
void menu_load(void)
{
    unsigned char file[HEADER + SLOTS];
    long long size = 0;
    unsigned got = 0, want;
    int kind = -1, ok, s, count;
    FileHandle h;
    if (dirty || moved)
        return;
    for (s = 0; s < SLOTS; s++)
        cheat_values[s] = 0;
    if (nn_fs_GetEntryType(&kind, PATH) || kind != 1)           /* none yet (1 is a file) */
        return;
    if (nn_fs_OpenFile(&h, PATH, 1))
        return;
    ok = !nn_fs_GetFileSize(&size, h) && size >= HEADER;
    want = ok ? (size < (long long)sizeof file ? (unsigned)size : sizeof file) : 0;
    ok = ok && !nn_fs_ReadFile(&got, h, 0, file, want) && got == want;
    nn_fs_CloseFile(h);
    if (!ok || file[0] != 'P' || file[1] != '3' || file[2] != 'C' || file[3] != 'M' ||
        (file[4] | file[5] << 8) != LAYOUT_VERSION)
        return;                                                 /* another layout of slots: every row off, and the next write replaces it */
    count = file[6] | file[7] << 8;
    if (count > SLOTS)
        count = SLOTS;                                          /* slots a later version of the menu added: not ours to read */
    if (HEADER + count > (int)want)
        return;
    for (s = 0; s < count; s++)
        if (file[HEADER + s] > SLOT_VALUES[s])
            return;                                             /* a value its row does not have: not read */
    for (s = 0; s < count; s++)
        cheat_values[s] = file[HEADER + s];
}

/* after the game writes its settings (setting.sav), before its caller commits the save: the menu's */
void menu_save(void)
{
    unsigned char file[HEADER + SLOTS];
    int kind = -1, flush = 1, s, ok;
    FileHandle h;
    if (!dirty && !moved)
        return;
    file[0] = 'P';
    file[1] = '3';
    file[2] = 'C';
    file[3] = 'M';
    file[4] = LAYOUT_VERSION & 0xff;
    file[5] = LAYOUT_VERSION >> 8;
    file[6] = SLOTS & 0xff;
    file[7] = SLOTS >> 8;
    for (s = 0; s < SLOTS; s++)
        file[HEADER + s] = cheat_values[s];
    if (nn_fs_GetEntryType(&kind, PATH) && nn_fs_CreateFile(PATH, sizeof file))
        return;
    if (nn_fs_OpenFile(&h, PATH, 2))
        return;
    ok = !nn_fs_SetFileSize(h, sizeof file) && !nn_fs_WriteFile(h, 0, file, sizeof file, &flush);
    nn_fs_CloseFile(h);                                         /* closed before the commit: an open file would fail it */
    if (ok)
        dirty = moved = 0;
}

/* -- the Onion menu's columns 6 and 7 --
 *
 * The Onion menu keeps a record of 0x48 bytes for each of its six columns from menu+0x5b0, five
 * types and "all" (the sixth), and touches them only by fixed offsets: it has no room for more.
 * Its counts are kept by type (seven rows, menu+0x55c), so taking Pikmin out and putting them back
 * (OK) already knows Purple and White. The mod's layout has columns 6 and 7 (N_PikBtn_05 and _06,
 * copies of column 4); this code runs them for the sixth and seventh types listed, in records of
 * its own laid out as the game's, doing what the game's code does for a column of its own (each
 * function below says which of the game's it follows). With five types or fewer listed (always,
 * with Story Purple And White off) the menu is the game's.
 */
#define ONION_COLUMNS 5             /* the game's type columns; its record 5 is "all" */
#define EXTRA_COLUMNS 2             /* the mod's */
#define ONION_TYPES 7               /* every type, in the menu's order */
#define INPUT_POINTER(i)    (*(char **)((i) + 0x490))      /* the input's pointer state: +0x18 is 0 while the pointer is not in use */
#define ONION_LAST_KEYS(m)  AT(m, 0x51a, unsigned char)    /* the stick and keys were in use last frame (not the pointer) */
#define ONION_LATCH(m)      AT(m, 0x519, unsigned char)    /* "can't" sounded: not again until the stick is let go */
#define ONION_TICKS(m)      AT(m, 0x51c, int)              /* a held change's ticking sound */
#define ONION_FIELD2(m)     AT(m, 0x520, int)              /* a second count the game takes from the field's room */
#define ONION_LISTED(m)     AT(m, 0x524, int)              /* types in the game's columns */
#define ONION_CLOSING(m)    AT(m, 0x52c, unsigned char)    /* OK or Back pressed */
#define ONION_NUMBER(m)     AT(m, 0x53c, void *)           /* the Number animation: frame = types listed - 1 */
#define ONION_ALL_NUMBER(m, s) AT(m, 0x540 + 4 * (s), void *)   /* the overlay's two parts' own: types - 2 */
#define ONION_FIELD(m)      AT(m, 0x558, int)              /* Pikmin in the field */
/* a type's counts, by its place in the menu's order: [0] in the Onion, [1] in the squad, [2] the change being made */
#define ONION_ROW(m, t)     ((int *)((char *)(m) + 0x55c) + 3 * ((unsigned)(t) < ONION_TYPES ? (unsigned)(t) : 0u))
#define ONION_RECORD(m, k)  ((Column *)((char *)(m) + 0x5b0 + 0x48 * (k)))   /* the game's record of its column k */
#define ONION_OK(m)         AT(m, 0x760, void *)           /* the OK button */
#define VCALL(obj, off) ((*(void ***)(obj))[(off) / 4])    /* an object's virtual call at `off` */
#define PANE_X(p)       AT(p, 0x18, float)
#define SOUND_CHANGE 0x2b5          /* the Onion menu's sounds: a count changed, */
#define SOUND_CANT 0x2b7            /* it cannot change, */
#define SOUND_COLUMN 0x2b8          /* the cursor on another column */

typedef struct {                    /* a column, as the game keeps one */
    unsigned type;                  /* +0x00 its type, as its place in the menu's order (type_place) */
    void *box;                      /* +0x04 B_PikBtn_0n: the cursor's place */
    void *top, *bottom;             /* +0x08, +0x0c its buttons: the Onion's side, the squad's */
    void *loop[2];                  /* +0x10, +0x14 their arrows' ArrowLoop */
    void *colour[2];                /* +0x18, +0x1c the buttons' Color (frame = the type) */
    void *arrows;                   /* +0x20 Color through G_ArrowColor_0n */
    void *pattern;                  /* +0x24 the lower button's Pattern */
    void *stick[5];                 /* +0x28 the stick icon's In, Out, InfoDown, InfoUp, InfoUpDown */
    void *info, *info_next;         /* +0x3c, +0x40 the info animation playing, and the next */
    unsigned char info_reset, focused, pad[2];  /* +0x44 the next put back to its start, not played; +0x45 the column has the cursor */
} Column;
typedef char column_is_the_games_size[sizeof(Column) == 0x48 ? 1 : -1];

static void *onion;                         /* the Onion menu these were found in */
static Column extra[EXTRA_COLUMNS];         /* columns 6 and 7 */
static void *extra_text[EXTRA_COLUMNS][2];  /* their buttons' numbers' text boxes: the Onion's, the squad's */
static void *overlay_text[2][EXTRA_COLUMNS];    /* the "all" overlay's for them (upper part, lower) */
static void *overlay_number[2][ONION_TYPES];    /* the overlay's numbers' panes, by column */
static void *overlay_icon[2][ONION_TYPES];      /* its icons, by type */
static int number_value[EXTRA_COLUMNS][2];  /* what their numbers show: left in the Onion, in the squad */
static unsigned char extra_ready;           /* columns 6 and 7 found (the mod's layout), and places of the cursor */
static int extra_listed;                    /* how many of them hold a type: 0 to 2 */
static int extra_focus = -1;                /* the one the cursor is on */

static const char STICK[] = "In\0Out\0InfoDown\0InfoUp\0InfoUpDown";       /* the stick icon's animations, in the record's order */
static const char ICONS[] = "N_PikRed_00\0N_PikRock_00\0N_PikYellow_00\0N_PikPink_00\0N_PikBlue_00\0N_PikPurple_00\0N_PikWhite_00";

static void enable(void *a, int on)                             /* an animation running, or not (the animator's virtual call +0x10) */
{
    if (a)
        ((void (*)(void *, int))VCALL(a, 0x10))(a, on);
}

static int running(void *a)                                     /* whether an animation is running */
{
    return *(unsigned char *)((char *)a + 0x14) != 0;
}

static float frame_now(void *a)                                 /* an animation's frame now */
{
    return AT(a, 0x10, float);
}

static int same(const char *a, const char *b)                   /* two names the same (none if either is missing) */
{
    if (!a || !b)
        return 0;
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return *a == *b;
}

static const char *next_name(const char *s)                    /* the next of a list of names (STICK, ICONS) */
{
    while (*s)
        s++;
    return s + 1;
}

static int purple_white_on(void *m)     /* Story Purple And White on: its row, or its two types in columns 6 and 7 */
{
    return cheat_values[STORY_PURPLE_WHITE_SLOT] != 0 || (m == onion && extra_listed);
}

static void onion_sound(int id)                                 /* a sound, as the Onion menu plays its own */
{
    unsigned sound[0x40 / 4];
    void *player = sound_player;
    sound_settings_init(sound);
    ((void (*)(void *, void *, void *))VCALL(player, 0xc))(player, *(void **)(sound_names + 0x14 + 4 * id), sound);
}

static int room(void *m)                /* the field's room: 100 (60 on Ultra-Spicy) less the Pikmin out and every change */
{
    int n = is_ultra_spicy(game_state) ? 60 : 100, t;
    n = n - ONION_FIELD(m) - ONION_FIELD2(m);
    for (t = 0; t < ONION_TYPES; t++)
        n -= ONION_ROW(m, t)[2];
    return n;
}

static unsigned listed_type(void *m, int k)                     /* the k-th column's type: the game's first, then the mod's */
{
    return k < ONION_LISTED(m) ? ONION_RECORD(m, k < 6 ? k : 0)->type : extra[k - ONION_LISTED(m)].type;
}

static int all_listed(void *m)                                  /* the types listed: in the game's columns and the mod's */
{
    return ONION_LISTED(m) + (m == onion ? extra_listed : 0);
}

/* A number on screen is drawn by a counter (TextCounterControl, one to each number's part,
   PaNumber_00), not by its text box: as the layout is built the counter hides the box, and from
   then on it draws, every frame and in digits of its own, the int its +0x220 points to if it has
   one, or else the value its text's tag names (the HUD's variables, five to a list). The controls
   made with a layout are in a list (layout+0xa4: +8 the first, +4 the end, +0x10 where a
   control's link is in it). The window's own list may hold its parts' controls as well; to be
   sure of finding every one, the parts' own lists are looked through too. */
static void *counter_box(char *control)            /* the text box a counter was made for (its +0x200's first) */
{
    char *core = control + 0x200;
    void ***entries = *(void ****)(core + 0x10);
    return *(int *)(core + 8) > 0 && entries && entries[0] ? *entries[0] : 0;
}

static int link_counters(char *layout)             /* columns 6 and 7's numbers' counters pointed at number_value */
{
    char *list = layout ? *(char **)(layout + 0xa4) : 0, *node;
    int linked = 0, c, k;
    if (!list)
        return 0;
    for (node = *(char **)(list + 8); node && node != list + 4; node = *(char **)(node + 4)) {
        char *control = node - *(int *)(list + 0x10);
        void *box;
        if (*(const char **)control != text_counter_vtable || !(box = counter_box(control)))
            continue;
        for (c = 0; c < EXTRA_COLUMNS; c++)
            for (k = 0; k < 2; k++)
                if (box == extra_text[c][k] || box == overlay_text[k][c]) {
                    *(int **)(control + 0x220) = &number_value[c][k];
                    linked++;
                }
    }
    return linked;
}

/* -- after the Onion menu's setup: columns 6 and 7 found by number, as it finds its own -- */
void menu_onion_setup(void *m)
{
    char name[24], group[24];
    char *layout = LAYOUT(m), *part, *number;
    char *lists[1 + 4 * EXTRA_COLUMNS + 2 * (1 + EXTRA_COLUMNS)];
    void *memory = *(void **)(layout_memory + 0x18);
    const char *s;
    int c, k, side, n_lists = 0, linked = 0;
    onion = m;
    extra_ready = 0;
    extra_listed = 0;
    extra_focus = -1;
    lists[n_lists++] = layout;
    for (c = 0; c < EXTRA_COLUMNS; c++) {
        Column *x = &extra[c];
        int n = ONION_COLUMNS + c;
        unsigned char *b = (unsigned char *)x;
        for (k = 0; k < (int)sizeof *x; k++)
            b[k] = 0;
        name_of(group, "G_ArrowLoopT_", n);
        x->loop[0] = layout_group_animation(layout, memory, "ArrowLoop", group, 1);
        name_of(group, "G_ArrowLoopD_", n);
        x->loop[1] = layout_group_animation(layout, memory, "ArrowLoop", group, 1);
        name_of(group, "G_ArrowColor_", n);
        x->arrows = layout_group_animation(layout, memory, "Color", group, 1);
        name_of(name, "Pa_PikBtnT_", n);
        part = find_part(layout, name);
        x->colour[0] = part ? layout_animation_simple(part, memory, "Color", 1) : 0;
        x->top = find_button(m, name);
        number = find_part(part, "Pa_OniyonNumber_00");
        lists[n_lists++] = part;
        lists[n_lists++] = number;
        extra_text[c][0] = find_text(number, "T_Count_00");
        name_of(name, "Pa_PikBtnD_", n);
        part = find_part(layout, name);
        x->colour[1] = part ? layout_animation_simple(part, memory, "Color", 1) : 0;
        x->bottom = find_button(m, name);
        x->pattern = part ? layout_animation_simple(part, memory, "Pattern", 1) : 0;
        number = find_part(part, "Pa_PlayerPikNumber_00");
        lists[n_lists++] = part;
        lists[n_lists++] = number;
        extra_text[c][1] = find_text(number, "T_Count_00");
        name_of(name, "B_PikBtn_", n);
        x->box = find_pane(layout, name);
        name_of(name, "Pa_NunStick_", n);
        part = find_part(layout, name);
        for (k = 0, s = STICK; k < 5; k++, s = next_name(s))
            x->stick[k] = part ? layout_animation_simple(part, memory, s, 1) : 0;
        for (k = 0; k < 2; k++)
            if (!x->loop[k] || !x->colour[k] || !x->stick[k] || !extra_text[c][k])
                return;                                         /* not the mod's layout: the game's menu as it is */
        if (!x->box || !x->top || !x->bottom || !x->arrows || !x->pattern || !x->stick[4])
            return;
        if (as_onion_button(x->top))                            /* what the menu's setup does to its own buttons */
            *((unsigned char *)x->top + 0x7c) = 1;
        if (as_onion_button(x->bottom))
            *((unsigned char *)x->bottom + 0x7c) = 1;
    }
    for (side = 0; side < 2; side++) {
        part = find_part(layout, side ? "Pa_AllBtnDown_00" : "Pa_AllBtnTop_00");
        lists[n_lists++] = part;
        for (k = 0, s = ICONS; k < ONION_TYPES; k++, s = next_name(s))
            overlay_icon[side][k] = find_pane(part, s);
        for (k = 0; k < ONION_TYPES; k++) {
            name_of(name, "Pa_OniyonNumber_", k);
            overlay_number[side][k] = find_pane(part, name);
        }
        for (c = 0; c < EXTRA_COLUMNS; c++) {
            name_of(name, "Pa_OniyonNumber_", ONION_COLUMNS + c);
            number = find_part(part, name);
            lists[n_lists++] = number;
            overlay_text[side][c] = find_text(number, "T_Count_00");
        }
    }
    for (k = 0; k < n_lists; k++)
        linked += link_counters(lists[k]);
    if (linked != 4 * EXTRA_COLUMNS)
        return;                                                 /* a number without a counter of its own */
    extra_ready = 1;
}

/* -- after the menu makes its boxes places of the cursor: columns 6 and 7's, as its own -- */
void menu_onion_places(void *m)
{
    int c;
    if (m != onion || !extra_ready)
        return;
    for (c = 0; c < EXTRA_COLUMNS; c++) {
        cursor_add_pane(CURSOR(m), extra[c].box);
        cursor_set_pane_group(CURSOR(m), extra[c].box, 0);      /* the type columns' group (all: 1, OK: 2) */
        cursor_pane_reachable(CURSOR(m), extra[c].box, 0);
    }
}

/* OK's link across to the last column: all four of its links as the menu opens (how 1), that one
   alone as the menu makes it again later */
static void ok_link(void *m, int how)
{
    int to[4] = {3, 0, 0, 0}, none[4] = {5, 0, 0, 0};
    void *box;
    if (!extra_listed)
        return;
    box = extra[extra_listed - 1].box;
    if (how) {
        to[2] = (int)box;
        cursor_set_links(CURSOR(m), ONION_OK(m), to, none, none, none);
    } else
        cursor_link_left(CURSOR(m), ONION_OK(m), 3, 0, box, 0);
}

/* -- after the menu's links of the cursor, as it opens: sideways to the nearest by place, nothing up or down -- */
void menu_onion_links(void *m)
{
    int across[4] = {6, 0, 0, 0}, none[4] = {5, 0, 0, 0}, c;
    if (m != onion || !extra_ready)
        return;
    for (c = 0; c < EXTRA_COLUMNS; c++)
        cursor_set_pane_links(CURSOR(m), extra[c].box, across, none, across, none);
    ok_link(m, 1);
}

/* -- after the menu is put back as it was: columns 6 and 7's animations and flags too -- */
void menu_onion_reset(void *m)
{
    int c, k;
    if (m != onion || !extra_ready)
        return;
    for (c = 0; c < EXTRA_COLUMNS; c++) {
        void **a = &extra[c].loop[0];
        for (k = 0; k < 11; k++)                                /* +0x10 to +0x38, as the game stops its own */
            enable(a[k], 0);
    }
    for (c = 0; c < EXTRA_COLUMNS; c++) {
        extra[c].focused = 0;
        animation_rewind(extra[c].stick[0]);
        extra[c].info = 0;
        extra[c].info_next = 0;
    }
    extra_listed = 0;
    extra_focus = -1;
}

static void extra_buttons(void *m, Column *x)                  /* onion_column_buttons, for a column of the mod's */
{
    int *row = ONION_ROW(m, x->type), on = 0;
    ((void (*)(void *, int))VCALL(x->top, 0x28))(x->top, row[2] + row[1] > 0);       /* some to put back */
    if (row[2] < row[0])
        on = room(m) > 0;                                       /* some to take out, and room for them */
    ((void (*)(void *, int))VCALL(x->bottom, 0x28))(x->bottom, on);
}

/* -- after the menu writes its columns' numbers (into the HUD's variables, which hold five):
      columns 6 and 7's, where their counters read them (the overlay's too) -- */
void menu_onion_numbers(void *m)
{
    int c;
    if (m != onion || !extra_ready)
        return;
    for (c = 0; c < extra_listed; c++) {
        int *row = ONION_ROW(m, extra[c].type);
        number_value[c][0] = row[0] - row[2];                   /* left in the Onion */
        number_value[c][1] = row[1] + row[2];                   /* in the squad */
        extra_buttons(m, &extra[c]);
    }
}

static void extra_boxes(void *m, int all)                      /* Select All on or off, for columns 6 and 7 */
{
    int c;
    for (c = 0; c < EXTRA_COLUMNS; c++) {
        button_set_active(extra[c].top, !all);                  /* with Select All on, the type columns' buttons are off */
        button_set_active(extra[c].bottom, !all);
        cursor_pane_reachable(CURSOR(m), extra[c].box, !all);
    }
    if (!all)
        ok_link(m, 0);
}

static void overlay_icons(void *m, int n, const unsigned *place)
{
    /* the overlay's icons stand in the order the game lists types without Purple and White (Red, Rock,
       Yellow, Winged, Blue); with them, each listed type's icon goes over its column's number */
    int side, t, p;
    if (!purple_white_on(m) || n < 2)
        return;
    for (side = 0; side < 2; side++)
        for (t = 0; t < ONION_TYPES; t++) {
            void *icon = overlay_icon[side][t];
            for (p = 0; p < n && place[p] != (unsigned)t; p++)
                ;
            if (!icon)
                continue;
            if (p < n && overlay_number[side][p]) {
                PANE_X(icon) = PANE_X(overlay_number[side][p]);
                PANE_FLAGS(icon) |= SHOWN | MOVED;
            } else
                show_pane(icon, 0);
        }
}

/* -- after the menu lists its types: the sixth and seventh in columns 6 and 7 -- */
void menu_onion_list(void *m)
{
    char *state = game_state, *var;
    unsigned place[ONION_TYPES];
    int n = 0, k, c, player, pattern;
    if (m != onion || !extra_ready)
        return;
    extra_listed = 0;
    extra_focus = -1;
    var = game_hud ? *(char **)(game_hud + 0x48) : 0;
    /* the game's list: every merged type in the menu's order, if the Onion opened is merged (else its own
       type alone, one column); Bingo Battle's menus (mode 3, two players) keep five */
    if (state && var && *(int *)(state + 0x2f0) != 3 && onion_merged(state, *(unsigned *)(var + 0x7dc)))
        for (k = 0; k < ONION_TYPES; k++)
            if (onion_merged(state, type_order[k])) {
                int t = type_order[k];
                place[n++] = is_pikmin_type(t) && (unsigned)(t - 1) < 7 ? type_place[t - 1] : 0;
            }
    if (n > ONION_COLUMNS)
        extra_listed = n - ONION_COLUMNS;
    player = var ? *(int *)(var + 0x8d8) : 8;                   /* who opened it: the lower buttons' Pattern, as the game picks it */
    if (!is_leader(player))
        player = 8;
    pattern = player == 10 ? 2 : player == 9;
    for (c = 0; c < extra_listed; c++) {                        /* each column's type and colours, as the game sets its own */
        Column *x = &extra[c];
        x->type = place[ONION_COLUMNS + c];
        animation_set_frame((float)x->type, x->colour[0]);
        animation_set_frame((float)x->type, x->colour[1]);
        animation_set_frame((float)x->type, x->arrows);
        animation_set_frame((float)pattern, x->pattern);
    }
    if (extra_listed) {                                         /* the frames the game sets for how many it lists, for six or seven */
        animation_set_frame((float)(n - 1), ONION_NUMBER(m));
        animation_set_frame((float)(n - 2), ONION_ALL_NUMBER(m, 0));
        animation_set_frame((float)(n - 2), ONION_ALL_NUMBER(m, 1));
    }
    extra_boxes(m, 0);                                          /* the game's own Select All off ran before the columns were known */
    menu_onion_numbers(m);
    overlay_icons(m, n, place);
}

static int extra_cannot(void *m, int *row, int add)             /* the game's check of a change, for a column of the mod's: 0 if it can */
{
    int full;
    if (row[1] < 1 && row[0] < 1)
        return 1;                                               /* none of the type anywhere */
    if (add >= 1 && !(row[2] < row[0]))
        return 3;                                               /* none left in the Onion */
    if (add < 0 && !(row[2] + row[1] > 0))
        return 2;                                               /* none left in the squad */
    full = room(m) < 1;
    return add > 0 && full ? 4 : 0;                             /* the field is full */
}

static int extra_change(void *m, Column *x, int add, int quiet) /* the game's change of a count, for a column of the mod's */
{
    int *row = ONION_ROW(m, x->type), k;
    if (!extra_cannot(m, row, add)) {
        if (!quiet)
            onion_sound(SOUND_CHANGE);
        else
            ONION_TICKS(m) = 3;
        row[2] += add;
        for (k = 0; k <= ONION_COLUMNS; k++)
            onion_column_buttons(m, k);
        onion_write_numbers(m);                                 /* (and then menu_onion_numbers: columns 6 and 7's numbers and buttons) */
        return 1;
    }
    if (ONION_LATCH(m))
        return 0;
    ONION_LATCH(m) = 1;
    onion_sound(SOUND_CANT);
    return 0;
}

static int all_change(void *m, int add, int quiet)
{
    /* the game's change of "all", by type: the game's own checks a column's type but changes the row
       at the column's place, which is the same only while column n holds type n (no Purple or White listed) */
    int k, n = all_listed(m);
    if (onion_all_cannot(m, add)) {
        if (ONION_LATCH(m))
            return 0;
        ONION_LATCH(m) = 1;
        onion_sound(SOUND_CANT);
        return 0;
    }
    if (!quiet)
        onion_sound(SOUND_CHANGE);
    else
        ONION_TICKS(m) = 3;
    for (k = 0; k < n; k++) {
        int *row = ONION_ROW(m, listed_type(m, k));
        if (add < 1) {
            if (row[2] + row[1] > 0)
                row[2] += add;
        } else if (row[2] < row[0] && room(m) > 0)
            row[2] += add;
    }
    for (k = 0; k <= ONION_COLUMNS; k++)
        onion_column_buttons(m, k);
    onion_write_numbers(m);
    return 1;
}

/* -- instead of a column's count changed: "all" over every type listed, by type -- */
int menu_onion_change(void *m, unsigned column, int add, int quiet)
{
    if ((int)column >= ONION_COLUMNS && purple_white_on(m))
        return all_change(m, add, quiet);
    return orig_onion_change(m, column, add, quiet);
}

/* -- instead of the "all" totals (left in the Onion, here; in the squad, next): over the types
      listed, by type (the game's own adds the first rows, as many as are listed) -- */
int menu_onion_left(void *m, int listed)
{
    int k, n, sum = 0;
    if (!listed || !purple_white_on(m))
        return orig_onion_left(m, listed);
    for (k = 0, n = all_listed(m); k < n; k++) {
        int *row = ONION_ROW(m, listed_type(m, k));
        sum += row[0] - row[2];
    }
    return sum;
}

int menu_onion_out(void *m, int listed)
{
    int k, n, sum = 0;
    if (!listed || !purple_white_on(m))
        return orig_onion_out(m, listed);
    for (k = 0, n = all_listed(m); k < n; k++) {
        int *row = ONION_ROW(m, listed_type(m, k));
        sum += row[1] + row[2];
    }
    return sum;
}

/* -- instead of Select All on or off: columns 6 and 7's boxes and buttons with the game's -- */
void menu_onion_all(void *m, int on)
{
    orig_onion_all(m, on);
    if (m == onion && extra_ready)
        extra_boxes(m, on);
}

/* -- after OK or Back is handled: the boxes out of reach, as the game's -- */
void menu_onion_close(void *m)
{
    int c;
    if (m != onion || !extra_ready || !ONION_CLOSING(m))
        return;
    for (c = 0; c < EXTRA_COLUMNS; c++)
        cursor_pane_reachable(CURSOR(m), extra[c].box, 0);
}

/* -- before the menu handles a button's press: columns 6 and 7's (pressed by the pointer, or by touch) -- */
int menu_onion_press(void *m, SafeString *pressed, int quiet)
{
    const char *s;
    int c;
    if (m != onion || !extra_ready || !extra_listed)
        return 0;
    s = name_in(pressed);
    for (c = 0; c < extra_listed; c++) {
        int up = same(s, *(const char **)((char *)extra[c].top + 0x58));
        if (up || same(s, *(const char **)((char *)extra[c].bottom + 0x58))) {
            window_press_handled(m);
            extra_change(m, &extra[c], up ? -1 : 1, quiet);    /* the upper button puts back, the lower takes out */
            return 1;
        }
    }
    return 0;
}

static void column_arrows(Column *x)                           /* the game's rule for a column's arrows: they loop while its button is lit */
{
    int side;
    for (side = 0; side < 2; side++) {
        void *button = side ? x->bottom : x->top, *a = x->loop[side];
        if (*(unsigned *)((char *)button + 8) & 0x10) {         /* the button lit (the cursor or pointer on it) */
            if (!running(a)) {
                enable(a, 1);
                play(a);
            }
        } else if (running(a) && AT(a, 0x24, float) != 0.0f)
            enable(a, 0);
    }
}

/* -- instead of the arrows' loops started and stopped: with columns 6 and 7 listed, over all eight
      records. The loops start and stop only while every one is at frame 0, so all stay in step; the
      game's test sees its own twelve, and would start a column's arrows while 6's or 7's were
      half-way through a loop. -- */
void menu_onion_arrows(void *m)
{
    float most = 0.0f, f;
    int k, side;
    if (m != onion || !extra_ready || !extra_listed) {
        orig_onion_arrows(m);
        return;
    }
    for (k = 0; k <= ONION_COLUMNS; k++)
        for (side = 0; side < 2; side++) {
            f = frame_now(ONION_RECORD(m, k)->loop[side]);
            most = f > most ? f : most;
        }
    for (k = 0; k < EXTRA_COLUMNS; k++)
        for (side = 0; side < 2; side++) {
            f = frame_now(extra[k].loop[side]);
            most = f > most ? f : most;
        }
    if (most != 0.0f)
        return;
    for (k = 0; k <= ONION_COLUMNS; k++)
        column_arrows(ONION_RECORD(m, k));
    for (k = 0; k < EXTRA_COLUMNS; k++)
        column_arrows(&extra[k]);
}

static void extra_focus_now(void *m, char *input, int keys)     /* which of columns 6 and 7 has the cursor, as the game finds its own */
{
    char *pointer = INPUT_POINTER(input);
    int c;
    extra_focus = -1;
    if (keys) {
        void *place = current_place(pointer, pointer + 0xb8);  /* the cursor's place */
        for (c = 0; c < extra_listed; c++)
            if (place == cursor_pane_place(CURSOR(m), extra[c].box))
                extra_focus = c;
    } else {
        char *under = layout_pane_at(LAYOUT(m), (*(unsigned short *)(input + 0x20) & 1) ? (void *)(input + 0x208) : (void *)pointer_nowhere);
        if (under)
            for (c = 0; c < extra_listed; c++)
                if (same(*(const char **)(under + 0x58), *(const char **)((char *)extra[c].top + 0x58)) ||
                    same(*(const char **)(under + 0x58), *(const char **)((char *)extra[c].bottom + 0x58)))
                    extra_focus = c;
    }
}

static void extra_info(void *m, int keys)                       /* the stick icon of columns 6 and 7, as the game plays its own */
{
    int c;
    for (c = 0; c < EXTRA_COLUMNS; c++) {
        Column *x = &extra[c];
        void *now, *next;
        if (c != extra_focus || !keys) {                        /* the stick icon goes */
            if (!x->focused)
                continue;
            x->focused = 0;
            enable(x->stick[0], 0);
            animation_to_end(x->stick[0]);
            enable(x->stick[1], 1);
            play(x->stick[1]);
            continue;
        }
        if (!x->focused) {                                      /* it comes */
            x->focused = 1;
            enable(x->stick[1], 0);
            animation_to_end(x->stick[1]);
            enable(x->stick[0], 1);
            play(x->stick[0]);
        }
        /* (the game works out here what is left in the Onion and whether the game is on Ultra-Spicy,
           and uses neither: the column with the cursor always shows InfoUpDown, again each time it ends) */
        x->info_reset = 0;
        now = x->info;
        x->info_next = x->stick[4];
        if (now) {
            if (running(now) && AT(now, 0x24, float) != 0.0f) {
                float f = frame_now(now);
                if (f == (float)animation_last_frame(now) || frame_now(now) == 0.0f) {
                    enable(now, 0);
                    now = x->info;
                }
            }
            if (now && running(now))
                continue;
        }
        next = x->info_next;
        if (!next)
            continue;
        x->info = next;
        x->info_next = 0;
        if (x->info_reset) {
            x->info_reset = 0;
            animation_rewind(next);
            continue;
        }
        enable(next, 1);
        play(next);
    }
}

/* -- instead of the menu's frame: the game's, then the cursor, stick and icons of columns 6 and 7
      as it does them for its own -- */
void menu_onion_frame(void *m)
{
    unsigned char keys_before;
    char *input;
    unsigned pressed, held, sideways;
    int keys, was, add = 0, quiet = 0;
    if (m != onion || !extra_ready || !extra_listed) {
        orig_onion_frame(m);
        return;
    }
    keys_before = ONION_LAST_KEYS(m);                           /* the game's frame sets it again before it ends */
    orig_onion_frame(m);
    if (!((int (*)(void *))VCALL(m, 0xb0))(m))
        return;                                                 /* not open */
    input = window_input(m);
    keys = *(int *)(INPUT_POINTER(input) + 0x18) == 0;
    was = extra_focus;
    extra_focus_now(m, input, keys);
    if (keys_before && keys && extra_focus >= 0 && !ONION_CLOSING(m)) {
        pressed = INPUT_PRESSED(input);
        held = INPUT_HELD(input) | pressed;
        sideways = *(unsigned *)(input + 0x200) & 0xcc000;     /* held left or right: up and down do nothing */
        if ((held & 0x20000) && !sideways)                      /* down (the stick) */
            add = 1, quiet = !(pressed & 0x20000);
        else if ((held & 0x10000) && !sideways)                 /* up */
            add = -1, quiet = !(pressed & 0x10000);
        else if ((held & 0x2000) && !sideways)                  /* down (the D-pad: the game asks the stick's bit, so always quiet) */
            add = 1, quiet = !(pressed & 0x20000);
        else if ((held & 0x1000) && !sideways)
            add = -1, quiet = !(pressed & 0x10000);
        else if (!(*(unsigned *)(input + 0x200) & 0x33000)) {   /* nothing up or down held */
            ONION_LATCH(m) = 0;
            ONION_TICKS(m) = 0;
        }
        if (add)
            extra_change(m, &extra[extra_focus], add, quiet);
        if (was != extra_focus)
            onion_sound(SOUND_COLUMN);
    }
    extra_info(m, keys);
}
