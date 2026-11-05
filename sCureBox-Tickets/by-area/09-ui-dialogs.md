## Native UI dialogs — overview

All modals of the native Avalonia UI (`src/SCureBox.Ui`) are **in-shell** dialogs: there are no OS windows. A dialog is a view model deriving from `DialogViewModel<TResult>`; it is pushed onto `IDialogService` (a stack), and the shell's `DialogHost` control renders the top one over a dimmed, blurred page. The caller `await`s the dialog's result. Views are resolved from the view-model type via the `UiPages.Dialogs` map and `ViewLocator`. Design surface is 1600 x 1000 design pixels (the shell is scaled by `ShellScaler`, which belongs to the Native UI area).

Note: there are **no** Wi-Fi, NetBird, settings-sub-page or DVT-tool dialog classes in this area. The "DVT test requested from sCure Cloud" Start/Decline prompt is a `MessageDialogViewModel` with `StayUp = true` (see UIDLG-02).

| Dialog view model (view) | Result type | Width (design px) | Opened by |
|---|---|---|---|
| `MessageDialogViewModel` (`MessageDialogView`) | `bool` | 760 (default card) | Home (delete program confirm, tag job "Start this job?", "Cannot Start Cure" info), CureProcess (hardware refusal / run error info), CureHistory (delete run / delete all), Settings (Reboot confirm, heater sensor fault info), DevHdt (Abort Calibration confirm), `NfcJobService` (unknown tag), `RemoteConfirmPrompter` (DVT Start/Decline, `StayUp`) |
| `OnScreenKeyboardViewModel` (`OnScreenKeyboardView`) | `string` | 0 = full screen, or docked 500 px high | Setup (serial, device name), Settings (system name), Network (diagnostics address), MaterialEditor (program name), PrintHistory (From/To dates), OriginSignIn (web form fields; docked + masked) |
| `NumberPadViewModel` (`NumberPadView`) | `double?` | 560 | Editor step cards (temperature, time, UV intensity), Settings (chamber heating °C, manual date/time parts), DevHdt (HDT parameters), DevLedCalibration (zone factor, requested power) |
| `DevAuthDialogViewModel` (`DevAuthDialogView`) | `bool` | 560 | TopBar (10th Settings press), Settings (10th tap on the versions card), Setup (10th tap on the serial barcode label → unlocks manual serial entry) |
| `UsbFileBrowserDialogViewModel` (`UsbFileBrowserDialogView`) | `string?` | 900 | Setup (organization CSV), Settings (Link Organization CSV), ImportCsv dialog (program CSV) |
| `CriticalAlertDialogViewModel` | `bool` | 900 | Home Start Cure while a critical alert is active |
| `NitrogenOnlyDialogViewModel` | `bool` | full screen | Home Start Cure with an N₂-only program and nitrogen mode off |
| `PreflightDialogViewModel` | `FanTestResult?` | 760 | Home Start Cure (held across the page change; finished by CureProcess) |
| `FanFailDialogViewModel` | `bool` | 900 | Home (pre-flight fan failure), CureProcess (fan failure while running, LED panel not heating) |
| `HeaterFaultDialogViewModel` | `bool` | 900 | CureProcess (start refused by thermistor 9001/9010-9012 or 9006, thermistor fault while running, 9006 while running, run error from thermistor) |
| `PauseDialogViewModel` | `bool` | 900 | CureProcess Pause button |
| `PauseOverlayViewModel` | `bool` | full screen | CureProcess after a confirmed pause |
| `AbortDialogViewModel` | `bool` | 900 | CureProcess Abort button |
| `DoorOpenDialogViewModel` | `bool` | full screen | CureProcess when the door opens mid-run (created with `new`, ticked by the page) |
| `TemperatureWarningDialogViewModel` | `bool` | full screen | CureProcess temperature stall (Err 7004) |
| `CureCompleteDialogViewModel` | `bool` | full screen | CureProcess on run completion (created with `new`) |
| `PrintHistoryDialogViewModel` | `PrintHistoryResult?` | 1440 | Home "View All" |
| `MaterialEditorDialogViewModel` | `bool` | 1120 | Home "+ New", Edit (swipe tray), Duplicate |
| `ImportCsvDialogViewModel` | `IReadOnlyList<Material>` | 1400 | Home "CSV" |
| `StaticIpDialogViewModel` | `StaticIpConfig?` | 900 | Network "STATIC IP" |
| `SoftwareUpdateDialogViewModel` | `bool` | 820 | Settings "Update Software" |
| `VersionsDialogViewModel` | `bool` | 900 | Settings versions card button |
| `ComplianceDialogViewModel` | `bool` | 1040 | Settings compliance button |
| `OriginSignInDialogViewModel` | `OriginOrganization?` | 1440 embedded / 820 in-window | Setup and Settings "Sign in to Origin" |

---

### UIDLG-01 — Dialog infrastructure (base view model, dialog service stack, DialogHost, view mapping)
**Summary**
- **What it is for:** The shared system that shows every pop-up window (dialog) on the machine's touch screen, inside the app itself.
- **Problem it solves:** Without one common mechanism, each screen would build its own pop-ups, they would look and behave differently, and pop-ups opened over other pop-ups would be hard to manage.
- **How we solve it:** Each dialog returns an answer the caller waits for. Dialogs sit on a stack, only the top one is drawn over a blurred, dimmed page, with a short fade. Page changes close them, and the screensaver stays off.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `Dialogs/`, `Controls/DialogHost.axaml(.cs)`, `UiPages.cs`, `ViewLocator.cs`, `ViewModels/ShellViewModel.cs`, `Views/ShellView.axaml(.cs)` (dialog parts only)
**Goal:** Provide a single in-shell modal mechanism: dialog view models that resolve a typed `Task<TResult>`, a stack-based dialog service (a dialog can open over another, e.g. a keyboard over a form), and a host control that renders the top dialog as a centred card, full screen, or docked to the bottom half with the dialog below it still visible. Opening/closing fades in 240 ms and the page behind is shown as a blurred still.
**Depends on:** Native UI (shell, `ShellScaler`, navigation service, `IdleService`, theme tokens, `UiMotion`), DI container (`Microsoft.Extensions.DependencyInjection`), CommunityToolkit.Mvvm.
**Files to create:**
- `src/SCureBox.Ui/Dialogs/DialogViewModel.cs` — `public abstract partial class DialogViewModel : ObservableObject`, `public abstract class DialogViewModel<TResult> : DialogViewModel`
- `src/SCureBox.Ui/Dialogs/IDialogService.cs` — `public interface IDialogService`
- `src/SCureBox.Ui/Dialogs/DialogService.cs` — `public sealed class DialogService : IDialogService`
- `src/SCureBox.Ui/Controls/DialogHost.axaml` + `.axaml.cs` — `public partial class DialogHost : UserControl`
- `src/SCureBox.Ui/UiPages.cs` — `public static readonly IReadOnlyDictionary<Type, Type> Dialogs`, `ViewFor(Type)`, `DialogsAreValid()`
- `src/SCureBox.Ui/ViewLocator.cs` — `public sealed class ViewLocator : IDataTemplate`
**Public contract:**
- `DialogViewModel`: `public virtual bool CloseOnOverlayTap => false;` `public virtual double DesignWidth => 760;` (0 = full screen) `public virtual double DockedHeight => 0;` (> 0 = docked to bottom at that height) `public virtual bool KeepAcrossPageChange => false;` `public abstract void Cancel();` `internal virtual void OnShown() { }` `internal event EventHandler? Closed;` `protected void RaiseClosed()`.
- `DialogViewModel<TResult>`: private `TaskCompletionSource<TResult>` created with `TaskCreationOptions.RunContinuationsAsynchronously`; `public Task<TResult> Result`; `protected abstract TResult CancelResult { get; }`; `protected void Close(TResult result)` (calls `TrySetResult`; raises `Closed` only when it succeeded, so only the first close counts); `public override void Cancel() => Close(CancelResult);`.
- `IDialogService`: `DialogViewModel? Current { get; }` (top), `DialogViewModel? Below { get; }` (second from top), `event EventHandler? Changed;`, `Task<TResult> ShowAsync<TResult>(DialogViewModel<TResult> dialog);`, `Task<TResult> ShowAsync<TDialog, TResult>(Action<TDialog>? init = null) where TDialog : DialogViewModel<TResult>;`, `void CloseAll(bool pageChange = false);`.
- `DialogService(IServiceProvider services)`; registered `services.AddSingleton<IDialogService, DialogService>()`. Dialog view models themselves are NOT registered in DI; they are created with `ActivatorUtilities.CreateInstance<TDialog>(_services)`.
- `DialogHost` properties: `Dialog` (StyledProperty `DialogViewModel?`), `Below` (StyledProperty), read-only direct properties `DisplayDialog`, `HasDialog`, `FadeProgress` (0..1), `CardWidth` (default 760), `CardDialog`, `FullDialog`, `DockDialog`, `DockHeight`; `public bool IsFading`; `public void StepFade()`; `public static double Ease(double t) => t * t * (3 - 2 * t);` constants `public static readonly TimeSpan FadeDuration = 240 ms`, `public const int FadeSteps = 12`.
- `ShellViewModel`: `[ObservableProperty] DialogViewModel? _dialog;` `[ObservableProperty] DialogViewModel? _belowDialog;` subscribed to `dialogs.Changed` → `BelowDialog = dialogs.Below; Dialog = dialogs.Current;`.
**Behaviour & rules:**
1. `ShowAsync(dialog)`: subscribe `dialog.Closed` → remove it from the stack; push onto the stack; raise `Changed`; call `dialog.OnShown()`; return `dialog.Result`. `Remove` raises `Changed` only if the dialog was in the stack.
2. `ShowAsync<TDialog,TResult>(init)`: create via `ActivatorUtilities.CreateInstance<TDialog>(services)` (constructor dependencies come from DI, optional ones may be missing), run `init` on it (before it is shown), then `ShowAsync(dialog)`.
3. `CloseAll(pageChange)`: for a snapshot of the stack, `Cancel()` every dialog, except when `pageChange == true` and the dialog's `KeepAcrossPageChange` is true.
4. Shell: on every navigation, if `_dialogs.Current is not null`, call `_dialogs.CloseAll(pageChange: true)` (dialogs belong to the page that opened them).
5. Only the top dialog is rendered. When a non-docked dialog opens over another one, the lower dialog's view is discarded and rebuilt when it becomes top again (views must keep any state they need on the view model, e.g. editor strip offset).
6. DialogHost layout (`Relayout`) for the displayed top dialog: `docked = top.DockedHeight > 0`; `fullScreen = top.DesignWidth <= 0 && !docked`; the card shows `Below` when docked, nothing when full screen, else the top dialog. Card: centred (`VerticalAlignment.Center`), `Width = CardWidth` (dialog's `DesignWidth`, or 760 when it is ≤ 0), Padding 32, CornerRadius `RadiusXl`, 2 px `RingBrush` border, background `PopoverBrush` (#141414). When docked: card goes to the top with margin top 14, `MaxHeight = max(200, 1000 - DockedHeight - 28)`, `ClipToBounds = true`. Full screen: `FullContent` content control shows the dialog over the whole surface. Docked: `Dock` border at the bottom with `Height = DockedHeight`, background `BackgroundBrush`, 2 px top `RingBrush` border.
7. Overlay: a full-size `Border` with `OverlayBrush` (#99000000). A pointer press on it calls `Cancel()` on the current dialog only when `CloseOnOverlayTap` is true; the event is always marked handled.
8. Fade: when `Dialog` changes, `HasDialog = dialog != null`; if non-null set `DisplayDialog` and relayout; start the fade. A `DispatcherTimer` (interval `FadeDuration / FadeSteps` = 20 ms, priority Render) steps `FadeProgress` by 1/12 toward 1 (open) or 0 (closed); snaps to the target when within half a step; host `Opacity = Ease(progress)`; `IsHitTestVisible = progress > 0`. At target the timer stops; at 0 (closed) content is cleared (`DisplayDialog`, `CardDialog`, `FullDialog`, `DockDialog` = null, all parts hidden). If `UiMotion.Enabled` is false the fade is applied instantly (1 or 0). Only opacity animates (no scale / relayout of the page).
9. `Below` change while a dialog is shown → relayout.
10. Shell page blur (in `ShellView`): when `HasDialog` turns true, capture the page layer into a `RenderTargetBitmap` at scale `BlurScale = 0.08` (greyscale text AA) and show it as an `ImageBrush` (Stretch Fill) inside an opaque `BackgroundBrush` border above the page; its opacity follows `Ease(FadeProgress)`; dropped and disposed when the fade reaches 0. On a page change while a dialog stays up (held pre-check), re-capture after the next layout pass of the new page. While a dialog is up or fading (`DialogIsUp`), `RequestBringIntoView` events on any `ScrollContentPresenter` under the shell are handled (suppressed) so the page never scrolls behind the scrim.
11. `IdleService.Enabled` (screensaver) is false while `_dialogs.Current is not null`.
12. View resolution: `ViewLocator.Match` = data is `PageViewModel` or `DialogViewModel`; `Build` looks up `UiPages.ViewFor(type)`, instantiates with `Activator.CreateInstance` and sets `DataContext`; unknown → `TextBlock "No view for {TypeName}"`. `UiPages.Dialogs` maps exactly the 24 view models listed in the overview to their views. `DialogsAreValid()` = every key derives from `DialogViewModel`.
13. There is no keyboard (Escape) handling in the native shell, although the base-class comment mentions Escape. OPEN QUESTION: whether Escape should cancel the top dialog (not implemented in 1.0.152).
**Configuration:** none
**Acceptance criteria:**
- Awaiting `ShowAsync` completes with the value passed to `Close`; a second `Close` is ignored.
- Opening a dialog over another sets `Current` to the new one and `Below` to the first; closing the top restores `Current`.
- A docked keyboard (`DockedHeight` 500) over a NumberPad: card shows the NumberPad, card bottom ≤ dock top, dock top ≥ half of the shell height; `DockHeight == 500`.
- A keyboard with `Docked = false` renders in `FullDialog`, `DockDialog == null`, `DockHeight == 0`.
- Navigating to another page cancels all open dialogs except those with `KeepAcrossPageChange`.
- Overlay tap closes only dialogs with `CloseOnOverlayTap == true`.
- Screensaver is disabled while any dialog is open, re-enabled after `CloseAll`.
- Opening and closing a dialog moves neither the page nor the shell scale; the page is blurred while a dialog is open and unblurred after.
**Tests:** `DialogDockTests` (docked keyboard layout, screensaver suppression, non-docked full-screen keyboard), `DialogMotionTests` (no page movement / no shell scale change, no scroll-into-view), `DialogBlurTests` (still taken before fade, opaque base; dialog outliving its page gets a still of the new page), `ShellTests.Shell_blurs_the_page_while_a_dialog_is_open_and_unblurs_after`; a `UiPages.DialogsAreValid()` check.
**Reference (source):** `src/SCureBox.Ui/Dialogs/DialogViewModel.cs`, `src/SCureBox.Ui/Dialogs/IDialogService.cs`, `src/SCureBox.Ui/Dialogs/DialogService.cs`, `src/SCureBox.Ui/Controls/DialogHost.axaml(.cs)`, `src/SCureBox.Ui/UiPages.cs`, `src/SCureBox.Ui/ViewLocator.cs`, `src/SCureBox.Ui/ViewModels/ShellViewModel.cs`, `src/SCureBox.Ui/Views/ShellView.axaml(.cs)`, `src/SCureBox.Ui/Services/IdleService.cs`, `src/SCureBox.Ui/UiServiceCollectionExtensions.cs`, `tests/SCureBox.Ui.Tests/DialogDockTests.cs`, `DialogMotionTests.cs`, `DialogBlurTests.cs`

---

### UIDLG-02 — Generic message / confirm dialog (MessageDialog) and its call sites
**Summary**
- **What it is for:** One reusable pop-up for yes/no questions and simple messages, such as 'Delete this run?' or 'Reboot device?'.
- **Problem it solves:** Many screens need to confirm risky actions or show a short notice. A DVT test request from sCure Cloud must never be dismissed by accident.
- **How we solve it:** A single card with title, text, OK and optional Cancel, with red styling for destructive actions. A 'stay up' mode ignores outside taps and page changes, used for the cloud Start/Decline request.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/MessageDialogViewModel.cs`, `Views/Dialogs/MessageDialogView.axaml`
**Goal:** One reusable confirm/info card (replaces browser `confirm()`): title, body, optional Cancel, OK, destructive styling. It also carries the "must be answered on purpose" mode used for the sCure Cloud DVT Start/Decline request.
**Depends on:** UIDLG-01; Native UI (Home, CureProcess, CureHistory, Settings, DevHdt pages, `NfcJobService`, `RemoteConfirmPrompter`), Dvt-Hdt (RemoteConfirm request source).
**Files to create:** `ViewModels/Dialogs/MessageDialogViewModel.cs` — `public sealed partial class MessageDialogViewModel : DialogViewModel<bool>`; `Views/Dialogs/MessageDialogView.axaml(.cs)`.
**Public contract:**
- `public bool StayUp { get; set; }`; `CloseOnOverlayTap => !StayUp`; `KeepAcrossPageChange => StayUp`; `CancelResult => false`; DesignWidth default (760).
- `[ObservableProperty]` `string Title = ""`, `string Body = ""`, `string OkText = "OK"`, `string? CancelText = "Cancel"`, `bool Destructive`; `public bool HasCancel => CancelText is not null` (re-raised when `CancelText` changes).
- Commands: `OkCommand` → `Close(true)`; `CancelDialogCommand` → `Close(false)`.
**Behaviour & rules:**
1. Layout (vertical stack, spacing 24): Title (class `h2`, red when `Destructive`), Body (`sm muted`), right-aligned buttons: outline Cancel (text `CancelText`, visible only when `HasCancel`) then primary OK (`OkText`, solid red when `Destructive`).
2. Setting `CancelText = null` makes it a single-button info dialog.
3. Call sites (exact texts):
   - Settings Reboot: Title "Reboot device?", Body "", OkText "REBOOT"; true → restart flow.
   - Home delete program: Title `Delete “{name}”?`, Body "The program will be removed from this machine. This cannot be undone.", OkText "Delete", Destructive.
   - Home tag job: Title "Start this job?", Body "Job: {job}\nProgram: {material}\nPrinter: {printer}\nTag: {tag}", OkText "Start", CancelText "Cancel".
   - Home "Cannot Start Cure" info: Title "Cannot Start Cure", Body = "No program named “{material}” is on this machine" or "Close the door to start the cure", OkText "OK", no Cancel.
   - NfcJobService unknown tag: Title "No job for this tag", Body "Tag {tag} was read, but no job on this machine was sent with it.", OK only.
   - CureProcess start refused (non-thermistor) and run error (non-thermistor, not 6016): Title "Hardware: {message}", Body = error-registry description of the code or "The hardware refused the command", OK only; then go Home.
   - CureHistory delete: Title "Delete this run?", Body "{material} ({date}) and its report are deleted from the machine and from sCure Cloud. This cannot be undone.", OkText "Delete", Destructive. Delete all: Title "Delete the whole cure history?", Body "All {n} runs and their reports are deleted from the machine and from sCure Cloud. This cannot be undone.", OkText "Delete all", Destructive.
   - Settings chamber heating refused by thermistor (`IsA(code, 9001)` i.e. 9001 or 9010-9012, or 9006 / message contains "thermistor"): Title "Heater not started — temperature sensor not reading" (or frozen: "Heater not started — temperature reading frozen"), Body = Body + "\n\n" + Hint (texts in Strings.Settings HeaterFault*/HeaterFrozen*, mention Err 9010 / Err 9006), OK only, Destructive.
   - DevHdt abort: Title "Abort Calibration", Body "Abort HDT calibration? LEDs turn off immediately; collected data is preserved.", OkText "Abort Calibration", Destructive.
   - RemoteConfirmPrompter (DVT from sCure Cloud): Title "DVT test requested from sCure Cloud", Body "{test}\n{detail\n}\nNothing turns on until you press Start. Press Start only if the chamber is ready and it is safe to run this test now; the test may light the UV LEDs or heat the chamber.", OkText "Start", CancelText "Decline", `StayUp = true`. The prompter keeps one dialog per request id; when the cloud withdraws the request it calls `dialog.Cancel()`; the answer is passed to `RemoteConfirm.Resolve(id, start)`; an exception counts as Decline.
**Configuration:** none
**Acceptance criteria:**
- OK resolves true, Cancel resolves false, overlay tap resolves false (unless `StayUp`).
- With `StayUp`, overlay tap does nothing and a page change does not close it.
- `HasCancel` false hides the Cancel button.
- DVT request shows Start/Decline; Start is what the runner reads; a withdrawn request closes the dialog and counts as nothing; requests pending before UI start are shown.
**Tests:** `RemoteConfirmPrompterTests` (4 tests), `CureHistoryTests.A_run_is_deleted_after_confirming_and_goes_to_the_cloud_queue`, `HomeTests.A_user_program_is_duplicated_and_deleted_from_its_swipe_tray`, `CureProcessVmTests` (refusal flows).
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/MessageDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/MessageDialogView.axaml`, `src/SCureBox.Ui/Services/RemoteConfirmPrompter.cs`, `src/SCureBox.Ui/Services/NfcJobService.cs`, `src/SCureBox.Ui/ViewModels/Pages/HomeViewModel.cs`, `CureProcessViewModel.cs`, `CureHistoryViewModel.cs`, `SettingsViewModel.cs`, `DevHdtViewModel.cs`, `src/SCureBox.Ui/Resources/Strings*.cs`

---

### UIDLG-03 — On-screen QWERTY keyboard
**Summary**
- **What it is for:** The on-screen keyboard used to type text, like names, serial numbers and passwords, on the touch screen.
- **Problem it solves:** The machine has no physical keyboard and no system keyboard, so users could not type into text fields.
- **How we solve it:** A full-screen or half-screen keyboard with letters, a numbers/symbols layer and Shift. Password fields can be hidden with Show/Hide. Closing it always returns the typed text.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/OnScreenKeyboardViewModel.cs`, `Views/Dialogs/OnScreenKeyboardView.axaml`
**Goal:** Touch text entry for every text field (no OS keyboard). Full-screen by default, or docked to the bottom half so the form/page behind stays visible; optional password masking with Show/Hide. There is no cancel — the current text is always the result.
**Depends on:** UIDLG-01.
**Files to create:** `OnScreenKeyboardViewModel.cs` with `public enum KeyKind { Char, Backspace, Shift, Blank }`, `public sealed record KeyItem(string Label, KeyKind Kind, string Value = "", bool Red = false, bool Active = false);`, `public sealed partial class OnScreenKeyboardViewModel : DialogViewModel<string>`; `OnScreenKeyboardView.axaml(.cs)`.
**Public contract:**
- `DesignWidth => 0`; `[ObservableProperty] bool _docked`; `DockedHeight => Docked ? DockedDesignHeight : 0`; `public const double DockedDesignHeight = 500`; `public double StripHeight => Docked ? 84 : 120`; `CancelResult => Text`.
- `[ObservableProperty]` `string Text = ""`, `bool Numbers`, `bool Shift`, `IReadOnlyList<KeyItem> Row1/Row2/Row3`, `bool Masked`, `bool Reveal`.
- `ModeLabel => Numbers ? "ABC" : "?123"`; `DisplayText => Masked && !Reveal ? new string('•', Text.Length) : Text`; `RevealLabel => Reveal ? "Hide" : "Show"`.
- Commands: `KeyCommand(KeyItem)`, `BackspaceCommand`, `SpaceCommand`, `CommaCommand`, `PeriodCommand`, `ToggleModeCommand`, `ToggleRevealCommand`, `DoneCommand`, `CloseKeyboardCommand`.
**Behaviour & rules:**
1. Letter layer: Row1 = q w e r t y u i o p + Backspace key ("⌫", Red); Row2 = a s d f g h j k l; Row3 = Shift ("⇧", Active = Shift) + z x c v b n m ! ? + Shift. With Shift on, letters show/insert upper-case.
2. Number layer: Row1 = 1..0 + Backspace (Red); Row2 = @ # $ % & * - + ( ); Row3 = Blank + " ' : ; / \ = _ ~ + Blank (blank keys invisible and disabled).
3. Rows are rebuilt when `Numbers` or `Shift` changes. Counts: Row1 11, Row2 9 (letters) / 10 (numbers), Row3 11.
4. `Key`: Char → append `Value`, then Shift off (single-shot); Backspace → remove last char; Shift → toggle Shift; Blank → nothing.
5. Space/Comma/Period append " ", ",", "."; `Done` and `CloseKeyboard` both `Close(Text)`; `Cancel()` (overlay is not tappable — `CloseOnOverlayTap` default false — or page change) also yields `Text`.
6. Layout: background `BackgroundBrush`, margin 16, rows `Auto,*,*,*,*`. Value strip (height `StripHeight`, 2 px bottom line): `DisplayText` (xxl semibold, no wrap) + primary "|" caret; right: "Show/Hide" (visible only when `Masked`) and "Close Keyboard". Row2 has 48 px side margin. Bottom row columns 120/96/*/96/180: ModeLabel, ",", space (blank label), ".", "Done" (sky).
7. Callers set `Text` (initial value) in `init`; callers usually `Trim()` the result. Origin sign-in sets `Masked = field.IsPassword` and `Docked = true`.
**Configuration:** none
**Acceptance criteria:**
- Initial letters layer, `Row1[0].Label == "q"`, `Row1[10].Kind == Backspace`, `Row3[0].Kind == Shift`, ModeLabel "?123".
- Shift → "Q", typing appends "Q" and turns Shift off.
- Toggle mode → "ABC", `Row1[0] == "1"`, Row2 count 10, `Row3[0].Kind == Blank`.
- Text "ab" + Q + @ + , + . + space + backspace = "abQ@,."; Close Keyboard resolves "abQ@,.".
- Masked shows bullets until Reveal.
**Tests:** `DialogViewModelTests.Keyboard_layers_shift_and_commit`, `DialogDockTests` (docked/non-docked), `BootAndSetupTests.Setup_name_step_uses_the_on_screen_keyboard_and_persists_the_name`.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/OnScreenKeyboardViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/OnScreenKeyboardView.axaml`, `src/SCureBox.Ui/Resources/Strings.cs` (Keyboard)

---

### UIDLG-04 — Number pad
**Summary**
- **What it is for:** A number keypad for entering values like temperature, time and UV power.
- **Problem it solves:** Users could enter numbers outside the allowed range or with the wrong number of decimals.
- **How we solve it:** The keypad knows the minimum, maximum, step and decimals. It blocks digits that go over the limit, has +/- buttons, and returns a clamped, rounded value, or nothing on Cancel.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/NumberPadViewModel.cs`, `Views/Dialogs/NumberPadView.axaml`
**Goal:** Numeric entry with min/max/step, optional decimals and a unit suffix; it refuses keys that would exceed the range's digit count or the maximum, and returns the clamped, rounded value (null on cancel).
**Depends on:** UIDLG-01.
**Files to create:** `NumberPadViewModel.cs` — `public sealed partial class NumberPadViewModel : DialogViewModel<double?>`; `NumberPadView.axaml(.cs)`.
**Public contract:**
- `CloseOnOverlayTap => true`; `DesignWidth => 560`; `CancelResult => null`.
- `[ObservableProperty]` `string Title = ""`, `double Min = 0`, `double Max = 100`, `double Step = 1`, `int Decimals = 0`, `string Suffix = ""`, `string Entry = ""`, `bool Negative` (unused by logic).
- `AllowDecimal => Decimals > 0`; `MaxWholeDigits => max(1, digits of floor(|Max|))`; `RangeText => $"{Min:0.##} – {Max:0.##}{Suffix}"`; `Display => (Entry == "" ? "0" : Entry) + Suffix`; `Value` = invariant parse of Entry or null; `IsValid => Value in [Min, Max]`.
- `public void SetValue(double? value)`; commands `DigitCommand(string)`, `DotCommand`, `BackspaceCommand`, `ClearCommand`, `IncrementCommand`, `DecrementCommand`, `OkCommand` (CanExecute = `IsValid`), `CancelDialogCommand`.
**Behaviour & rules:**
1. `SetValue(v)`: Entry = `Format(v)` (rounded to `Decimals`, format `"0." + '#' x Decimals`, invariant) or ""; marks the entry "untouched" when non-empty.
2. `Digit(d)`: start from "" if untouched or Entry == "0", else Entry; clear untouched; next = start + d; refuse if the whole part (before ".") is longer than `MaxWholeDigits`, or if next parses to a value > Max; else Entry = next. (So 30-80 °C takes two digits; 10-100 % three; a preloaded value is replaced by the first digit.)
3. `Dot`: ignored if `!AllowDecimal`; if untouched → Entry "0."; ignored if Entry already has "."; else append "." ("0." when empty).
4. Backspace removes the last char; Clear empties; both clear untouched.
5. Increment/Decrement: Entry = Format(clamp((Value ?? Min) ± Step, Min, Max)); sets untouched.
6. OK: `Close(Math.Round(Math.Clamp(Value ?? Min, Min, Max), Decimals))`.
7. Every change to Entry/Min/Max refreshes `IsValid` and `OkCommand.CanExecute`.
8. Layout: Title (h2); a secondary panel with "−" button, `Display` (xxl semibold), "+" button; `RangeText` (xs muted); 3x4 keypad 1-9, ".", 0, backspace (red); bottom row "C" (outline), "Cancel" (outline), "OK" (primary). "." is disabled when `!AllowDecimal`.
9. Call-site ranges: editor step temperature/time/UV (min/max from the step card, step = nudge, suffix "°C" / " min" / "%"); Settings chamber heating (HeatingMinC..HeatingMaxC, step 1, "°C", preset current or min); Settings manual date/time: Day 1-31, Month 1-12, Year 2020-2099, Hour 0-23, Minute 0-59; DevHdt: HDT 30-150 step 1, stability band 0.5-10 step 0.5 (1 dec), safety margin 0-10 step 0.5 (1 dec), stability time 1-30 step 1, max rate 0-5 step 0.1 (1 dec); DevLedCalibration zone factor FactorMin..FactorMax step 0.01 (2 dec), requested power 0-100 step 5 "%".
**Configuration:** none
**Acceptance criteria:**
- Min 25, Max 80, Step 5, "°C", SetValue(40): Display "40°C", RangeText "25 – 80°C"; Increment → 45; Clear, "9","9" → Entry "9" (99 refused), invalid, OK disabled; Dot ignored; backspace, "7","5", Increment → 80; OK → 80.
- Min 0, Max 1.5, Decimals 2: "1",".","2","3","4" → Entry "1.234"; OK → 1.23.
- Cancel → null.
- Intensity 10-100 accepts three digits only to reach 100; Bleaching 1-720 min takes three digits; first digit replaces a preloaded value.
**Tests:** `DialogViewModelTests.NumberPad_clamps_rounds_and_respects_decimals`, `NumberPadTests` (5 tests), `EditorTests.Tapping_the_temperature_opens_the_keypad_with_the_process_range`, `EditorTests.Tapping_the_time_and_the_intensity_opens_the_keypad`.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/NumberPadViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/NumberPadView.axaml`, `src/SCureBox.Ui/ViewModels/Editor/StepCardViewModel.cs`, `src/SCureBox.Ui/ViewModels/Pages/SettingsViewModel.cs`, `DevHdtViewModel.cs`, `DevLedCalibrationViewModel.cs`

---

### UIDLG-05 — Developer Mode PIN pad (DevAuth)
**Summary**
- **What it is for:** A 4-digit PIN pad that unlocks Developer Mode.
- **Problem it solves:** Developer tools must not be open to normal operators, but engineers need a quick way in on the machine.
- **How we solve it:** After 10 taps on a hidden spot, a PIN pad opens. The right PIN turns on Developer Mode; a wrong PIN shows 'Incorrect password' and clears the entry.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/DevAuthDialogViewModel.cs`, `Views/Dialogs/DevAuthDialogView.axaml`
**Goal:** Four-digit PIN entry that unlocks Developer Mode through `DevModeService.TryPassword`. Wrong PIN shows "Incorrect password" and clears.
**Depends on:** UIDLG-01; Native UI (`DevModeService`, TopBar, Settings, Setup pages).
**Files to create:** `DevAuthDialogViewModel.cs` — `public sealed partial class DevAuthDialogViewModel : DialogViewModel<bool>` (ctor `DevAuthDialogViewModel(DevModeService dev)`); `DevAuthDialogView.axaml(.cs)`.
**Public contract:** `public const int Length = 4;` `public static readonly TimeSpan CheckDelay = 150 ms;` `CloseOnOverlayTap => true`; `DesignWidth => 560`; `CancelResult => false`; `Title` "Developer Mode", `Description` "Enter the Developer Mode password", `ErrorText` "Incorrect password"; `[ObservableProperty] string Entry`, `bool Error`; `Dot1..Dot4 => Entry.Length >= n`; commands `DigitCommand(string)` (async), `BackspaceCommand`, `CancelDialogCommand`.
**Behaviour & rules:**
1. `Digit(d)`: ignore if Entry already has 4 chars; Error = false; append; if length < 4 return; wait `CheckDelay` (150 ms); `_dev.TryPassword(Entry)` → true: `Close(true)`; false: Error = true, Entry = "".
2. `DevModeService.TryPassword` compares to the constant password `"8176"`, logs to the dev log ("Developer Mode authentication failed/successful", "Developer Mode entered"), sets `IsDev = true` and raises `Changed`.
3. Layout: amber 96 px rounded square with Terminal icon; Title (h2); Description (xs muted); four 28 px ring dots (filled amber when on, red stroke when Error); error line (opacity bound to Error, fixed height 32); 3x4 keypad 1-9, blank, 0, backspace; full-width outline "Cancel".
4. Openers: TopBar Settings button — `DevModeService.RegisterSettingsPress()` returns true on the 10th press (`PressesToUnlock = 10`) when not in dev mode → dialog; true → navigate to DevMenu. Settings: the 10th tap on the versions card (`DevTapsToUnlock = 10`) → dialog; true → DevMenu. Setup serial step: the 10th tap on the barcode label (`ManualEntryTaps = 10`) → dialog; true → `_dev.Exit()` immediately and unlock manual serial entry via the keyboard.
**Configuration:** none (PIN is the constant `DevModeService.Password`).
**Acceptance criteria:**
- Entering 8176 resolves true and puts the app in dev mode; a wrong 4-digit PIN sets Error, clears Entry, stays open.
- A fifth digit is ignored; backspace removes one digit; Cancel/overlay resolve false.
**Tests:** `DevTests.Dev_auth_pin_flow_enters_developer_mode_and_the_menu_guards`.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/DevAuthDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/DevAuthDialogView.axaml`, `src/SCureBox.Ui/Services/DevModeService.cs`, `src/SCureBox.Ui/ViewModels/TopBarViewModel.cs`, `SettingsViewModel.cs`, `SetupViewModel.cs`

---

### UIDLG-06 — USB file browser
**Summary**
- **What it is for:** A simple file picker that shows matching files (for example CSV files) on plugged-in USB drives.
- **Problem it solves:** There is no normal file dialog on the machine, so users could not choose a file from a USB stick.
- **How we solve it:** It scans all USB drives, the top folder and two levels down, skipping hidden folders, lists up to 200 matching files, and returns the full path of the file the user taps.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/UsbFileBrowserDialogViewModel.cs`, `Views/Dialogs/UsbFileBrowserDialogView.axaml`
**Goal:** Minimal file picker (replaces the browser file dialog) listing files that match a pattern on every mounted USB drive, root plus two directory levels; result is the chosen full path or null.
**Depends on:** UIDLG-01; Application-Platform (`IUsbMounts`).
**Files to create:** `UsbFileBrowserDialogViewModel.cs` — `public sealed record UsbFileItem(string Name, string Path, string Drive);` `public sealed partial class UsbFileBrowserDialogViewModel : DialogViewModel<string?>` (ctor `(IUsbMounts usb)`, calls `Refresh()`); view.
**Public contract:** `public const int MaxDepth = 2; public const int MaxFiles = 200;` `CloseOnOverlayTap => true`; `DesignWidth => 900`; `CancelResult => null`; `[ObservableProperty] string Title = "Select organization CSV"`, `string Pattern = "*.csv"`, `IReadOnlyList<UsbFileItem> Files`; `IsEmpty`; `EmptyText` "No CSV file found on a USB drive"; `[RelayCommand] public void Refresh()`; `PickCommand(UsbFileItem)` → `Close(item.Path)`; `CancelDialogCommand`.
**Behaviour & rules:**
1. `Refresh`: for each mount in `IUsbMounts.Mounts()` (writable first), Drive = last path segment of the mount (trimmed of '/' '\'), or the mount itself if empty; `Scan(mount, drive, depth 0)`; stop at 200 files.
2. `Scan`: `Directory.GetFiles(dir, Pattern)` sorted ordinal-ignore-case, add until 200; then if depth < 2, recurse into subdirectories whose names do not start with "."; IOException / UnauthorizedAccessException are swallowed (directory skipped).
3. Changing `Pattern` re-scans.
4. Layout: header USB icon + Title (h2) + ghost Refresh icon button; EmptyText (centred) when empty; otherwise a scroll list (max height 520) of secondary buttons: FileText icon (yellow), Name (sm medium, ellipsis), Drive (xxs mono muted), chevron; right-aligned outline "Cancel".
5. Openers set `Title`: Setup "Select organization CSV", Settings "Select organization CSV", ImportCsv "Select program CSV". Callers read the file with `File.ReadAllText`; read errors are handled by the caller (Setup/Settings treat content as "" → "No valid organization ID found in CSV file"; ImportCsv adds a failed row "Cannot read file: {error}").
**Configuration:** none
**Acceptance criteria:**
- Lists matching files at depth 0-2 across all mounts, skips dot-directories, caps at 200, empty state text shown with no files.
- Tapping a file resolves its full path; Cancel/overlay resolves null.
**Tests:** covered indirectly by `BootAndSetupTests.Setup_org_step_parses_the_uuid_and_completes_setup`, `SettingsTests.Organization_csv_needs_a_uuid`, `EditorTests.Csv_import_adds_a_valid_file_and_reports_a_bad_one`. OPEN QUESTION: no dedicated unit test of the scan exists in 1.0.152; add one (temp directory tree, depth/dot/limit cases).
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/UsbFileBrowserDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/UsbFileBrowserDialogView.axaml`, `src/SCureBox.Application/Platform/IUsbMounts.cs`

---

### UIDLG-07 — Start Cure gate dialogs: Critical alert, Nitrogen-only, System pre-check spinner
**Summary**
- **What it is for:** The checks shown when the user presses Start Cure: critical alerts, nitrogen-only programs and the system pre-check.
- **Problem it solves:** A cure must not start with a critical alert active, or with a nitrogen-only program while nitrogen is off. The fans must be tested first, without the screen freezing.
- **How we solve it:** Start Cure shows the critical alerts or a nitrogen warning and stops. Otherwise a spinning-fan screen runs the fan test and stays up until the cure screen gets its first real status, at most 45 seconds.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/{CriticalAlertDialogViewModel,NitrogenOnlyDialogViewModel,PreflightDialogViewModel}.cs`, matching views
**Goal:** The dialogs Home's Start Cure passes through: refuse with a list of critical alerts, refuse an N₂-only program when nitrogen is off, then show a spinning-fan "Running System Pre-Check" while the all-fans test runs; the pre-check can stay up across the page change until CureProcess has the run's first real status.
**Depends on:** UIDLG-01, UIDLG-08; Native UI (Home, CureProcess, `AlertService`, navigation); Application-Process (`ICureController.RunFanTest`, `FanTestResult`).
**Files to create:** `CriticalAlertDialogViewModel : DialogViewModel<bool>`, `NitrogenOnlyDialogViewModel : DialogViewModel<bool>`, `PreflightDialogViewModel : DialogViewModel<FanTestResult?>` (ctor `(ICureController controller, ILogger<PreflightDialogViewModel> log)`), and views `CriticalAlertDialogView`, `NitrogenOnlyDialogView`, `PreflightDialogView`.
**Public contract:**
- CriticalAlert: `CloseOnOverlayTap => true`, `DesignWidth => 900`, `CancelResult => false`; `Title` "Critical alert active"; `Body` "A cure cannot start while a critical alert is active. Handle it/them on the Alerts screen first:"; `[ObservableProperty] IReadOnlyList<string> Lines`; `public void Load(AlertService alerts)`; `CloseDialogCommand` → false; `GoToAlertsCommand` → true.
- NitrogenOnly: `DesignWidth => 0`, `CancelResult => false`; `Title` "Cannot Start Cure", `Line1` "This material contains only nitrogen purge steps, but nitrogen is not enabled on the system.", `Line2` "Enable nitrogen in Settings or choose a different material.", `OkText` "OK"; `OkCommand` → true.
- Preflight: `public static readonly TimeSpan HoldLimit = 45 s`; `DesignWidth => 760`; `CancelResult => _result` (the fan test result so far); `Hint` "Running System Pre-Check"; `public bool HoldAfterTest { get; set; }`; `KeepAcrossPageChange => HoldAfterTest`; `public Task<FanTestResult?> TestCompleted`; `public void Finish() => Close(_result)`.
**Behaviour & rules:**
1. CriticalAlert `Load`: take at most 4 entries of `alerts.Critical`, each line `"{code} — {message}"` or `"{code} — {message} ({detail})"` when detail is non-blank (message from `alerts.Registry.Message(code)`). Layout: red AlertTriangle + Title (h2 destructive), Body, lines indented 24, buttons "Close" (outline) and "Go to alerts" (primary). Home: true → navigate to Alerts (replace: false).
2. NitrogenOnly is full screen on `Background95Brush`: 160 px red-dim circle with 96 px AlertTriangle, Title, Line1, Line2, large primary OK. Shown when every step is Nitrogen and `UiSettingsStore.NitrogenMode` is false.
3. Home Start Cure order: if `_alerts.HasCritical` → CriticalAlert; if door open → return silently; nitrogen-only check; then Preflight with `HoldAfterTest = true`.
4. Preflight `OnShown` (async): `_result = await Task.Run(() => controller.RunFanTest("all"))` (exception → warning log, result stays null); complete `TestCompleted`; if not held → `Close(_result)`; if held → wait `HoldLimit` (45 s), log a warning if still open, then `Finish()` (so it can never hang the screen).
5. Home after `TestCompleted`: compute failed fans; if any → `Finish()`, await the dialog, then show FanFail (Preflight kind, UIDLG-08); false → stop; true → `SetFanOverride(fan, true)` for each failed fan. Then navigate to CureProcess with a `CureStartRequest` whose `Preflight` is the still-open dialog (or null). CureProcess calls `Finish()` when the first status with `State != "preflight"` arrives, when the start fails / material missing, or when leaving the page.
6. Preflight view: a 72 px cyan Fan icon with class `spin` rotating 0→360° in 1.4 s, infinite, linear (style animation on `RotateTransform.Angle`, origin 50%,50%) + Hint text.
**Configuration:** none
**Acceptance criteria:**
- Start with a critical alert opens CriticalAlert; Go to alerts navigates to Alerts.
- N₂-only program with nitrogen mode off opens NitrogenOnly and does not navigate.
- Start runs the pre-flight fan test and navigates to CureProcess; the spinner stays up until CureProcess finishes it.
- Preflight view has exactly one IconGlyph of kind Fan with class "spin" and one style with one 1.4 s infinite animation with 2 keyframes.
**Tests:** `HomeTests.Start_with_a_critical_alert_opens_the_critical_dialog`, `HomeTests.Nitrogen_only_material_without_nitrogen_mode_is_refused`, `HomeTests.Start_runs_the_preflight_fan_test_and_navigates_to_CureProcess`, `HomeTests.FailedFans_reads_the_fan_test_result`, `DialogViewModelTests.Preflight_dialog_spins_the_fan_glyph`.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/CriticalAlertDialogViewModel.cs`, `NitrogenOnlyDialogViewModel.cs`, `PreflightDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/CriticalAlertDialogView.axaml`, `NitrogenOnlyDialogView.axaml`, `PreflightDialogView.axaml`, `src/SCureBox.Ui/ViewModels/Pages/HomeViewModel.cs` (StartCure), `CureProcessViewModel.cs` (EndPreflight)

---

### UIDLG-08 — Fan / LED-panel failure dialog
**Summary**
- **What it is for:** A warning that shows which fans are not turning or which LED panels are not heating, before or during a cure.
- **Problem it solves:** Broken fans or LED panels can harm the machine or ruin the cure, and the operator needs to know what failed.
- **How we solve it:** The dialog lists the failed parts, explains what happened and what it means, and lets the operator stop or choose 'Continue anyway', which is saved as an override.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/FanFailDialogViewModel.cs`, `Views/Dialogs/FanFailDialogView.axaml`
**Goal:** Tell the operator which fans did not rotate (before or during a cure) or which LED panels did not heat, and let them stop or explicitly continue anyway (recorded as an override).
**Depends on:** UIDLG-01; Native UI (Home, CureProcess, LED heat check); Application-Process (`SetFanOverride`); Domain (error codes 9002/9003, 9040/9041/9044/9045).
**Files to create:** `FanFailDialogViewModel.cs` with `public enum FanFailKind { Fan, Led }`, `public enum FanFailWhen { Preflight, Running }`, `public sealed partial class FanFailDialogViewModel : DialogViewModel<bool>`; view.
**Public contract:** `DesignWidth => 900`; `CancelResult => false`; `[ObservableProperty]` `FanFailKind Kind`, `FanFailWhen When`, `IReadOnlyList<string> Items`, `string Title`, `string Explanation`, `string Consequence`, `string StopLabel`; `ContinueLabel` "Continue anyway"; `public void Setup(FanFailKind kind, FanFailWhen when, IReadOnlyList<string> ids)`; `ContinueAnywayCommand` → true; `StopCommand` → false.
**Behaviour & rules:**
1. Items: Led → `"{panel name} — did not heat up"` with names left/right/back/door → "Left/Right/Back/Door LED panel" (unknown id kept); Fan → `"{fan name} — not rotating"` with FAN_LEFT "Left LED fan", FAN_RIGHT "Right LED fan", FAN_BACK "Back LED fan", FAN_DOOR "Door LED fan", FAN_HEATER "Heater fan", FAN_COOLING "Chamber intake fan" (unknown id kept).
2. Title: Led "Cure stopped — LED panel not heating"; Fan+Preflight "Fan failure — process not started"; Fan+Running "Cure stopped — fan failure".
3. Explanation: Led = "The UV was on for 15 s (30 s at low power) and this panel's temperature sensor did not rise while the others did: ... Every output was switched off and the program is paused where it was." (full text in `Strings.FanFail.ExplainLed`); Preflight "All fans were tested before starting; the one above did not turn."; Running "Every output was switched off and the program is paused where it was."
4. Consequence: Led `Strings.FanFail.ConsequenceLed`, Fan `Strings.FanFail.ConsequenceFan` (texts in Strings.cs).
5. StopLabel: Preflight "Cancel", Running "Stop process".
6. Layout: red AlertTriangle + Title (h2); red-dim bordered box listing Items each with a red Fan icon; Explanation (muted); Consequence; buttons Stop (outline) and "Continue anyway" (solid destructive).
7. Callers: Home pre-flight (true → `SetFanOverride(fan, true)` per fan, then start); CureProcess running fan failure (runner paused; false → abort; true → overrides + resume); CureProcess LED not heating (raises one alert per panel first: 9040/9041/9044/9045 via `ErrorCodes.LedNotHeatingOf`, fallback 9004; false → abort; true → `LedCheck.Override(panels)` + resume).
**Configuration:** none
**Acceptance criteria:**
- Fan/Preflight with FAN_DOOR, FAN_HEATER → Title "Fan failure — process not started", Items ["Door LED fan — not rotating", "Heater fan — not rotating"], StopLabel "Cancel".
- Led/Running with "left" → Title "Cure stopped — LED panel not heating", Items[0] "Left LED panel — did not heat up", StopLabel "Stop process"; Continue anyway resolves true.
**Tests:** `DialogViewModelTests.FanFail_dialog_texts_follow_kind_and_moment`, `CureProcessVmTests.Fan_failure_pauses_and_continue_anyway_overrides_the_fan`.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/FanFailDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/FanFailDialogView.axaml`, `src/SCureBox.Ui/Resources/Strings.cs` (FanFail), `HomeViewModel.cs`, `CureProcessViewModel.cs`

---

### UIDLG-09 — Heater fault dialog (chamber thermistor not reading / reading frozen)
**Summary**
- **What it is for:** A warning that the chamber heater was not started or was turned off because the temperature sensor is not reading or is stuck.
- **Problem it solves:** Heating with a broken or frozen temperature sensor is unsafe, because the machine cannot see how hot the chamber is.
- **How we solve it:** The dialog explains the sensor fault (Err 9010 or 9006), offers Retry where it makes sense, and never offers 'continue anyway'.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/HeaterFaultDialogViewModel.cs`, `Views/Dialogs/HeaterFaultDialogView.axaml`
**Goal:** Explain that the heater was not started / was switched off because the chamber thermistor is open (Err 9010; `ErrorCodes.IsA(code, TempSensorDisconnected=9001)` matches 9001 and 9010-9012) or its reading is frozen (Err 9006); offer Retry where it makes sense, never "continue anyway".
**Depends on:** UIDLG-01; Native UI (CureProcess); Domain (ErrorCodes 9001 family, 9006).
**Files to create:** `HeaterFaultDialogViewModel.cs` with `public enum HeaterFaultWhen { Start, Running }`, `public sealed partial class HeaterFaultDialogViewModel : DialogViewModel<bool>`; view.
**Public contract:** `DesignWidth => 900`; `CancelResult => false`; `[ObservableProperty]` `HeaterFaultWhen When = Running`, `string Message = ""`, `bool ShowRetry = true`, `string StopLabel = "Stop process"`, `bool Frozen`; computed `Title`, `SensorLine`, `Body`, `Footnote`, `RetryLabel` "Retry", `HasMessage`; `public void Init(HeaterFaultWhen when, string? message, bool showRetry = true, string? stopLabel = null, bool frozen = false)`; `RetryCommand` → true; `StopCommand` → false.
**Behaviour & rules:**
1. `Init`: sets fields; StopLabel default = Running ? "Stop process" : "Cancel"; raises Title/SensorLine/Body/Footnote/HasMessage.
2. Texts — not frozen: Title Running "Heater switched off — temperature sensor not reading", Start "Heater not started — temperature sensor not reading"; SensorLine "Heater temperature sensor (chamber) — no reading"; Body Running/Start = `Strings.CureDialogs.HeaterBodyRunning/HeaterBodyStart`; Footnote "Check the chamber thermistor cable and its connector on the IO board, then press Retry / try again. Err 9010 is on the Alerts screen."
3. Frozen: Title Running "Heater switched off — temperature reading frozen", Start "Heater not started — temperature reading frozen"; SensorLine "Heater temperature reading (chamber) — not moving"; Body `FrozenBodyRunning/FrozenBodyStart`; Footnote "Check that TEMP_CHAMBER is the real chamber NTC, seated in the chamber, on the right IO-board connector. Err 9006 is on the Alerts screen."
4. Layout: red AlertTriangle + Title (h2, width 760); red-dim box with Thermometer icon + SensorLine (semibold) and Message (xs muted mono, only if non-blank); Body; Footnote; buttons StopLabel (outline) and Retry (primary, visible when ShowRetry).
5. Callers (CureProcess): start refused with a code where `ErrorCodes.IsA(code, 9001)` (9001 or 9010-9012), or 9006, or message containing "thermistor" → `Init(Start, message, frozen: code == 9006)`; true → retry the start; false → go Home. Running thermistor fault → runner paused, `Init(Running, detail)`; true → resume, false → abort. Running frozen (9006) → `Init(Running, detail, showRetry: false, stopLabel: "Stop process", frozen: true)` then abort. Run ended in error with thermistor code/message → `Init(Running, message, showRetry: false, stopLabel: "OK")` then Home.
**Configuration:** none
**Acceptance criteria:**
- Start refusal by the heater sensor offers Retry and Retry restarts the program start.
- Running heater fault Stop aborts and goes Home.
- Frozen mode shows the frozen texts and hides Retry when `showRetry: false`.
**Tests:** `CureProcessVmTests.Heater_fault_stop_aborts_and_goes_home`, `CureProcessVmTests.Start_refusal_by_the_heater_sensor_offers_retry`.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/HeaterFaultDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/HeaterFaultDialogView.axaml`, `src/SCureBox.Ui/Resources/Strings.Cure.cs` (CureDialogs), `CureProcessViewModel.cs`

---

### UIDLG-10 — Pause, Pause overlay (door-gated Continue) and Abort dialogs with hot-chamber caution
**Summary**
- **What it is for:** The dialogs for pausing or aborting a running cure, plus the 'paused' screen.
- **Problem it solves:** Users could pause or abort by mistake, continue with the door open, or touch hot parts inside the chamber.
- **How we solve it:** Pause and Abort ask for confirmation. The paused screen allows Continue only while the door is closed. All show a hot-surface warning that turns red at 40 C or more.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/{PauseDialogViewModel,PauseOverlayViewModel,AbortDialogViewModel}.cs`, views; `Views/Dialogs/AbortDialogView.axaml.cs` (contains `HotSurfaceSign`); `ViewModels/Cure/HotChamber.cs`
**Goal:** Confirm pause (heating/UV/gas stop, door released), then show a full-screen paused overlay whose Continue is enabled only while the door reads closed; confirm abort. All three show a hot-surface caution that turns red at ≥ 40 °C.
**Depends on:** UIDLG-01; Native UI (CureProcess page, `MachineStateStore`); Application-Process (runner pause/resume/abort, `OpenDoor`).
**Files to create:** `PauseDialogViewModel : DialogViewModel<bool>`, `PauseOverlayViewModel : DialogViewModel<bool>` (ctor `(MachineStateStore store)`), `AbortDialogViewModel : DialogViewModel<bool>`, `public static class HotChamber`, `public class HotSurfaceSign : Control`, views `PauseDialogView`, `PauseOverlayView`, `AbortDialogView`.
**Public contract:**
- `HotChamber`: `public const double HotC = 40;` `IsHot(double? t) => t >= 40`; `Title(t)` = hot ? "Caution — hot surfaces inside." : "Caution — hot surface"; `Body(t)` = hot ? "The chamber is at {t:0.#}°C. Wear heat-resistant gloves and avoid contact with the chamber and the model." : "The chamber and the model may still be warm — wear gloves when handling."
- Pause & Abort: `DesignWidth => 900`, `CancelResult => false`, `[ObservableProperty] double? ChamberTemp`, `IsHot`, `HotTitle`, `HotBody` (re-raised on ChamberTemp change), `public void Init(double? chamberTemp)`. Pause: `Title` "Pause the Process?", `Body` (Strings.CureDialogs.PauseBody), `Note` (PauseNote), `KeepRunning` "Keep Running", `PauseAndOpen` "Pause & Open Door"; `KeepCommand` → false, `PauseCommand` → true. Abort: `Title` "Stop the Cure Process?", `Body` (AbortBody), `Bullet1`, `Bullet2`, `KeepRunning`, `YesStop` "Yes, Stop"; `KeepCommand` → false, `StopCommand` → true.
- PauseOverlay: `DesignWidth => 0`, `CancelResult => false`; `[ObservableProperty]` `string PhaseName`, `bool? DoorClosed`, `double? ChamberTemp`, `bool ApiConnected = true`; `Title` "Process Paused — Door Released"; `Body` "Heating, UV and gas are off. The {phase} step is on hold and will continue exactly where it stopped."; `DoorIsClosed => DoorClosed == true`; `GateText` = closed ? "Door closed — press Continue to resume heating and UV." : "Close the chamber door to continue."; `CanContinue => DoorIsClosed || !ApiConnected`; `StopText` "Stop Process", `ContinueText` "Continue"; `public void Init(string phaseName)`; `public void Refresh()`; `ContinueCommand` (CanExecute `CanContinue`) → true; `StopCommand` → false.
- `HotSurfaceSign`: `StyledProperty<double> SizeProperty` default 72; measures Size x Size; renders in a 100x100 box scaled by Size/100: yellow (#F5C400) triangle `M50 7 L95 88 H5 Z` with 5 px ink (#111111) round-join outline, ink base bar rect (30,70,40,7) radius 1.5, three heat waves (path in source) stroked 5 px round caps.
**Behaviour & rules:**
1. PauseOverlay reads `store.ApiConnected`, `store.State.DoorClosed`, `store.State.ChamberTemp` in the constructor and on every `store.Updated` (subscribed in `OnShown`, unsubscribed on `Closed`). Door/API changes refresh `DoorIsClosed`, `GateText`, `CanContinue` and `ContinueCommand.CanExecute`.
2. CureProcess Pause: only if not finished, running, and no dialog open → PauseDialog(Init chamber temp); true → pause runner, `controller.OpenDoor()` (refusal logged), then PauseOverlay(Init phase label of current step); true → resume runner; false → abort.
3. CureProcess Abort: after the run finished it just goes Home; else if no dialog open → AbortDialog; true → abort now.
4. Layouts: Pause — cyan-dim 96 px square with PauseCircle + Title (title class); Body; yellow note box with AlertTriangle + Note; caution box (muted bg; red-dim + red border and red title when hot; title orange otherwise) with HotSurfaceSign 72 + HotTitle/HotBody; buttons "Keep Running" (outline), cyan "Pause & Open Door" with DoorOpen icon. Abort — yellow 96 px square with black AlertTriangle + Title; Body; two bullets with Eye and Box icons; caution box; buttons "Keep Running" (outline), "Yes, Stop" (solid destructive). PauseOverlay — full screen `Background95Brush`, 1000 wide centred stack: cyan 128 px circle DoorOpen icon, Title, Body, caution box, GateText (green when closed, orange otherwise), large buttons "Stop Process" (destructive, Square icon) and "Continue" (primary, Play icon when enabled, Lock icon when not, `IsEnabled = CanContinue`).
**Configuration:** none
**Acceptance criteria:**
- Pause shows the modal, then the door-gated overlay; Continue disabled while door open, enabled when closed or when the API is disconnected; Continue resumes the runner.
- Abort "Yes, Stop" aborts the runner and returns Home; "Keep Running" changes nothing.
- Chamber at 45 °C → `IsHot`, title "Caution — hot surfaces inside.", body contains "45°C"; null/39 °C → warm texts.
**Tests:** `CureProcessVmTests.Pause_shows_the_modal_then_the_door_gated_overlay_and_resumes`, `CureProcessVmTests.Abort_dialog_yes_stop_aborts_the_runner_and_goes_home`, `CureProcessTests.Pause_opens_the_door_gated_overlay_and_resume_continues`, `CureProcessTests.Abort_dialog_yes_stop_aborts_the_runner_and_returns_home`.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/PauseDialogViewModel.cs`, `PauseOverlayViewModel.cs`, `AbortDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/PauseDialogView.axaml`, `PauseOverlayView.axaml`, `AbortDialogView.axaml(.cs)`, `src/SCureBox.Ui/ViewModels/Cure/HotChamber.cs`, `CureProcessViewModel.cs`

---

### UIDLG-11 — Cure-run overlays: Door open countdown, Temperature warning, Cure complete
**Summary**
- **What it is for:** Full-screen messages during a cure: door opened, temperature not reached, and cure finished.
- **Problem it solves:** The operator must know when the door is open mid-run, when the chamber cannot reach its target temperature, and when the cure is done.
- **How we solve it:** A 10-second countdown asks to close the door. A temperature warning (Err 7004) asks Continue or Abort. A completion screen shows time, steps, report status and an Open Door button.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/{DoorOpenDialogViewModel,TemperatureWarningDialogViewModel,CureCompleteDialogViewModel}.cs`, views
**Goal:** Full-screen overlays the CureProcess page drives: a 10-second door-open countdown (no buttons), a temperature-stall warning (Err 7004) asking Continue/Abort, and the completion screen with an Open Door button and a report-saved line.
**Depends on:** UIDLG-01; Native UI (CureProcess, `CureFormat`, cure report builder); Domain (ErrorCodes 7004, 6016).
**Files to create:** `DoorOpenDialogViewModel : DialogViewModel<bool>`, `TemperatureWarningDialogViewModel : DialogViewModel<bool>`, `CureCompleteDialogViewModel : DialogViewModel<bool>`, views.
**Public contract:**
- DoorOpen: `public const int GraceSeconds = 10;` `DesignWidth => 0`; `CancelResult => false`; `[ObservableProperty] int Countdown = 10`; `Title` "Door Open — Process Paused", `Body` "The chamber door was opened during an active process. The process cannot continue while the door is open.", `CountdownText` "Close the door now, or the process will be aborted in", `SecondsText` "seconds"; `Init(int seconds = GraceSeconds)`, `Tick()` (Countdown = max(0, Countdown-1)), `Dismiss()` → `Close(true)`.
- TemperatureWarning: `DesignWidth => 0`; `CancelResult => true` (dismissed = keep going); `[ObservableProperty] double? Target, Current`; `Title` "Temperature Warning"; `Body` "The system is unable to reach the target temperature of {target:0.# or --}°C. Current temperature: {current:0.# or --}°C."; `Note` "Continuing may cause distortion of the printed models."; `Question` "Do you want to continue?"; `AbortText` "Abort", `ContinueText` "Continue"; `Init(double? target, double? current)`; `ContinueCommand` → true, `AbortCommand` → false.
- CureComplete: `DesignWidth => 0`; `CancelResult => false`; `[ObservableProperty]` `string MaterialName`, `string TotalTime = "00:00"`, `int Steps`, `string ReportMessage = ""`; `Title` "Cure Complete!", `Body` "The curing process for {material} has been completed successfully.", `TotalTimeText` "Total time: {mm:ss}", `StepsText` "{n} steps", `OpenDoorText` "Open Door", `HasReportMessage`; `Init(string material, double totalSeconds, int steps)` (TotalTime = `CureFormat.MinSec(totalSeconds)`); `OpenDoorCommand` → true.
**Behaviour & rules:**
1. DoorOpen: CureProcess creates it with `new`, `Init()`, shows it (not awaited) on the first update with the door open mid-run; ticks once per second of door-open updates; on door close / run end calls `Dismiss()`. The machine itself latches the door abort (Err 6016) — the UI then goes Home (6016 stays on the Alerts screen). Layout: 75 % black backdrop, zinc-900 card 900 wide with 4 px red border: red AlertTriangle 88, Title, Body (zinc-300), CountdownText (bold), Countdown number (5xl bold red), SecondsText.
2. TemperatureWarning: CureProcess raises alert 7004 with detail "No temperature progress toward {t}°C (now {c}°C)" then shows the dialog; true → reset stall detector; false → abort. Layout: full screen `Background95Brush`, yellow-dim circle AlertTriangle, Title, Body, Note (yellow), Question, large "Abort" (destructive) and "Continue" (primary).
3. CureComplete: created with `new`, `Init(MaterialName, status.TotalElapsedSec, phaseCount)`, shown; the cure report is built on a worker thread; when it was saved OK the page sets `dialog.ReportMessage = "Saved to USB"` on the UI thread (empty = silent). Result true → delete pending print rows and `controller.OpenDoor()`; then Home. Layout: full screen, green-dim 192 px circle CheckCircle, Title (2xl), Body, row TotalTimeText (cyan) + StepsText, ReportMessage (green, only if set), large primary "Open Door" button with DoorOpen icon (min height 96).
**Configuration:** none
**Acceptance criteria:**
- Door countdown starts at 10, decrements per Tick, never below 0, Dismiss resolves true.
- Temperature warning body formats null as "--"; dismissal resolves true.
- A single cooling step completes and shows the completion overlay; Open Door goes Home; without USB the report is kept silently (no ReportMessage).
**Tests:** `CureProcessVmTests.Completion_shows_the_overlay_builds_the_report_and_open_door_goes_home`, `CureProcessVmTests.Completion_without_usb_keeps_the_report_silently`, `CureProcessTests.A_single_cooling_step_completes_and_shows_the_completion_overlay`; door/stall flows in `CureProcessVmTests`.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/DoorOpenDialogViewModel.cs`, `TemperatureWarningDialogViewModel.cs`, `CureCompleteDialogViewModel.cs`, views of the same names, `CureProcessViewModel.cs` (DoorOpened, StallWarningAsync, CompleteAsync, BuildReport)

---

### UIDLG-12 — Print history dialog (filters, multi-select, Cure Together)
**Summary**
- **What it is for:** A list of the organization's print jobs, used to pick what to cure next.
- **Problem it solves:** Users need to find the right print quickly, choose the right program for it, and cure several prints together only when they use the same material.
- **How we solve it:** The list shows newest first with material, printer and date filters. A tap picks the print's material; a multi-selection of one material can be cured together.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/PrintHistoryDialogViewModel.cs`, `Views/Dialogs/PrintHistoryDialogView.axaml`
**Goal:** Show the organization's print jobs newest first with material / printer / date filters; a tap picks a print's material; a multi-selection restricted to one material can be cured together.
**Depends on:** UIDLG-01, UIDLG-03; Application (`IPrintHistoryStore`, `IMaterialStore`); Domain (`PrintLog`, `Material`, `ProgramEstimator.PrintMinutes`); Native UI (`UiSettingsStore.HasOrganization`, `CureFormat`, Home).
**Files to create:** `PrintHistoryDialogViewModel.cs` containing `public sealed record PrintHistoryResult(string MaterialName, IReadOnlyList<string> PrintIds);`, `public sealed partial class PrintHistoryDialogViewModel : DialogViewModel<PrintHistoryResult?>` (ctor `(IPrintHistoryStore prints, UiSettingsStore settings, IDialogService dialogs, IMaterialStore? materials = null)`, calls `Load()`), `public sealed partial class PrintRowViewModel : ObservableObject`, `public sealed partial class FilterChipViewModel : ObservableObject`; view.
**Public contract:**
- Dialog: `DesignWidth => 1440`; `CancelResult => null`; collections `Rows`, `MaterialChips`, `PrinterChips`; `[ObservableProperty]` `bool ShowFilters`, `string? MaterialFilter`, `string? PrinterFilter`, `string FromText`, `string ToText`, `string TitleText`, `string SelectedText`, `string SelectionMessage`, `bool IsMixed`, `bool CanCure`, `int FilterCount`, `string EmptyText`; `HasOrganization`, `SelectedCount`, `HasSelection`, `HasFilters`, `IsEmpty`, `HasSelectionMessage`, `FilterCountText`, `FromDisplay`/`ToDisplay` (placeholder "yyyy-mm-dd"), labels (`FiltersLabel` "Filters", `MaterialLabel` "Material", `PrinterLabel` "Printer", `FromLabel` "From:", `ToLabel` "To:", `ClearLabel` "Clear", `ClearSelectionLabel` "Clear Selection", `CloseLabel` "Close", `CureTogetherLabel` "Cure Together"), `IReadOnlySet<string> SelectedIds`; methods `Load()`, `Filtered()`, `Tap(PrintRowViewModel)`, `Toggle(PrintRowViewModel)`; commands `ToggleFiltersCommand`, `ClearFiltersCommand`, `ClearSelectionCommand`, `CloseDialogCommand` (→ null), `CureTogetherCommand` (CanExecute `CanCure`), `EditFromCommand`, `EditToCommand`.
- `PrintRowViewModel(PrintHistoryDialogViewModel dialog, PrintLog log, bool showPrinter, IEnumerable<Material>? programs = null)`: `Log`, `Id`, `PrintName`, `MaterialName`, `PrinterName`, `ShowPrinter`, `DateText` (`CureFormat.DateTimeShort`), `DurationText` ("{n:0} min" from `ProgramEstimator.PrintMinutes(log, programs)`), `IsOk` (status completed/ok/success), `IsWarning` (aborted/warning/partial), `IsError` (otherwise), `[ObservableProperty] bool IsSelected`, `TapCommand`, `ToggleCommand`.
- `FilterChipViewModel(string label, string? value, Action<string?> apply)`: `Label`, `Value`, `[ObservableProperty] bool IsActive`, `PickCommand`.
**Behaviour & rules:**
1. `Load`: all prints ordered by parsed date descending (unparsable = min); chips: "All Materials" (null) + distinct non-empty material names sorted; "All Printers" (null) + distinct printers sorted; then `Apply`.
2. `Filtered`: material/printer equality; From = `CureFormat.ParseDay(FromText)`, To = ParseDay(ToText)+1 day; a print with an unparsable date is excluded when a date bound is set; `d >= from` and `d < to`.
3. `Apply` (on any filter change): rebuild Rows (programs = presets + user materials when the store is present), keep selection flags; FilterCount = count of set filters (dates only when they parse); chip `IsActive` = chip value equals filter; TitleText "Print History ({shown})" or "Print History ({shown}/{total})"; EmptyText "No print history yet." when no prints at all else "No results match the filters."
4. Selection: SelectedText "— {n} selected"; distinct materials of the selection: 0 → message "", 1 & one row → "Ready to cure {material}", 1 & many → "Ready to cure {n}× {material}", >1 → "⚠ Cannot cure different materials together!" with `IsMixed`; `CanCure = exactly one material`.
5. Row tap: with no selection → `Close(new PrintHistoryResult(row.MaterialName, [row.Id]))`; otherwise toggle the row. The checkbox button toggles.
6. Cure Together: `Close(new PrintHistoryResult(material, selected ids))` only when exactly one material.
7. Date fields: open the keyboard (`Text` = current), result trimmed into FromText/ToText.
8. Home: result null → nothing; picks the material row by name (none → nothing); remembers PrintIds as pending (deleted after a completed run); if more than one id and Start is possible → starts the cure.
9. Layout: header TitleText (h2) + SelectedText + outline "Filters" toggle with a count badge; collapsible filter bar (Material chips wrap; Printer chips only when `HasOrganization`; From/To date buttons (mono, min width 200); "Clear" ghost when HasFilters); selection message card (green, red when mixed); rows list (max height 520) — check box button, status icon (green check / orange triangle / red X), print name + material, date, duration (cyan), printer (only with organization), chevron; footer "Clear Selection" (ghost, when selection), "Close" (outline), "Cure Together" (primary, Play icon, visible when CanCure).
**Configuration:** none
**Acceptance criteria:**
- Home View All opens the dialog; a row tap with no selection selects that material on Home.
- Selecting two rows of different materials shows the mixed warning and hides Cure Together.
- Filters narrow rows and update the title count; Clear resets all four filters.
**Tests:** `CurePrintHistoryTests` (incl. `Home_View_All_opens_the_dialog_and_a_pick_selects_the_material`).
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/PrintHistoryDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/PrintHistoryDialogView.axaml`, `src/SCureBox.Ui/Resources/Strings.Cure.cs` (PrintHistory), `HomeViewModel.cs` (ViewAll)

---

### UIDLG-13 — Program (material) editor dialog
**Summary**
- **What it is for:** The editor where users build or change a cure program (material): its name and its steps.
- **Problem it solves:** Users need an easy touch way to create and edit programs, and must not save programs that are not valid.
- **How we solve it:** A pop-up with a name field, a sliding row of step cards with an Add Step tile, a summary, a check before saving, and export of the program to USB as CSV.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/MaterialEditorDialogViewModel.cs`, `Views/Dialogs/MaterialEditorDialogView.axaml(.cs)`
**Goal:** Modal over Home to build or edit a cure program: name (keyboard), a horizontal strip of inline-edited step cards plus an "Add Step" tile, CSV export to USB, a summary line, validation message and Save/Update Program. Result true when the material list changed.
**Depends on:** UIDLG-01, UIDLG-03, UIDLG-04; Native UI (`StepCardViewModel`, `IStepCardHost`, `StepCard` control, `EditorRules`, `Tween`, `AlertService`); Domain (`CureStep`, `Material`, `ProgramCsv`, `ProgramValidator`, `ProgramEstimator`, `ErrorCodes` 9081/9082); Application (`IMaterialStore`, `ISystemService.ExportCsv`).
**Files to create:** `MaterialEditorDialogViewModel.cs` — `public sealed partial class MaterialEditorDialogViewModel : DialogViewModel<bool>, IStepCardHost` (ctor `(IMaterialStore materials, ISystemService system, IDialogService dialogs, AlertService alerts, TimeProvider clock, ILogger<MaterialEditorDialogViewModel> log)`); `MaterialEditorDialogView.axaml(.cs)` — `public partial class MaterialEditorDialogView : UserControl`.
**Public contract:**
- `CloseOnOverlayTap => false`; `DesignWidth => 1120`; `CancelResult => _saved`.
- `ObservableCollection<StepCardViewModel> Cards`; `public double StripOffset { get; set; }`; `[ObservableProperty]` `string Name`, `bool IsEdit`, `string Summary`, `string? SaveError`, `string? CsvMessage`, `bool CsvOk`; `HeaderTitle` (IsEdit ? "Edit Program" : "Build Cure Program"), `SaveLabel` ("Update Program" / "Save Program"), `NameDisplay` (blank → "Tap to enter a name..."), `NameEmpty`, `HasSaveError`, `HasCsvMessage`, `CanDeleteSteps => Cards.Count > 0`, `IReadOnlyList<CureStep> Steps` (normalized from cards).
- Methods: `Init(object? parameter)`, `SetSteps(IReadOnlyList<CureStep>)`, `ApplyStep(int index, CureStep step)`, `ShowExportResult(ExportResultDto r)`, `bool TrySave()`; event `EventHandler<int>? StepAdded`; `IStepCardHost`: `Dialogs`, `StepsBefore(card)`, `DeleteStep(card)`, `StepEdited(card)`.
- Commands: `EditNameCommand`, `AddStepCommand`, `ExportCsvCommand`, `CancelDialogCommand`, `SaveCommand`.
- View: `public Tween Slide`, `public void RestoreOffset()`, `public void CenterStep(int index)`, `public static double CenterOffset(double cardLeft, double cardWidth, double viewport, double extent) => Math.Clamp(cardLeft + cardWidth/2 - viewport/2, 0, Math.Max(0, extent - viewport))`.
**Behaviour & rules:**
1. `Init(null)` → new program, IsEdit false, Name "", no steps. `Init(Material m)` → edit; Name = m.Name; steps = m.Steps.
2. `SetSteps`: `EditorRules.Normalize(steps)`, rebuild cards numbered from 1, refresh ranges & can-delete on each, update summary, clear SaveError. `ApplyStep(i, s)` replaces or appends then SetSteps. `DeleteStep` removes and SetSteps. `StepEdited` renumbers, refreshes ranges, clamps values, updates summary, clears SaveError. `StepsBefore(card)` = built steps of cards in front (all cards if the card is not yet in the list).
3. `AddStep`: append `EditorRules.NewStepFor(steps)` (sequence rules; defaults e.g. Heating 40 °C / 10 min), then raise `StepAdded(min(index, Cards.Count-1))`.
4. Summary: "{steps} steps · {round(HoldSeconds/60)} min holds · ~{EstimateProgramMinutes} min total".
5. `EditName`: keyboard with Text = Name; Name = result trimmed.
6. `ExportCsv`: csv = `ProgramCsv.ToCsv(Steps)`; file name = (blank Name ? "untitled" : Name.Trim()) + ".csv"; `Task.Run(() => system.ExportCsv(fileName, csv))`; exception → `{Ok=false, Message=e.Message, Code=9082}`; `ShowExportResult`: ok → CsvMessage = message or "Saved to USB" (green); fail → code 9081 → "No Disk-on-Key connected — connect one and try again", else message or "Could not save to the Disk-on-Key" (yellow); when a code is present raise it on `AlertService` with the message.
7. `TrySave`: `EditorRules.FirstError(Name, Steps)` — "Enter a material name", "Add at least one step", or the first `ProgramValidator` error mapped ("After an N₂ purge, add a Cure or Bleaching step", "Add a Cooling step after the Cure/Bleaching step that follows the N₂ purge", other messages with "N2 purge"→"N₂ purge") → SaveError, return false. Else material = existing (or new with CreatedAt = UTC now ISO "O") with Name trimmed, Steps, TotalDuration = `EstimateProgramMinutes`, IsPreset = false; replace by Id in user materials or append; `ReplaceUserMaterials`; `_saved = true`. `Save` → TrySave then `Close(true)`. Cancel returns `_saved`.
8. View: rows: header (HeaderTitle title class; "Name:" label; 520 wide pill button showing NameDisplay with Pencil icon) / 2 px line / horizontal ScrollViewer `StepScroll` containing `Strip` (height 600): the cards (StepCard control, spacing 20) + dashed 260x600 "Add Step" tile (Plus icon) / SaveError (red) / footer: "CSV" outline button (Download icon), Summary + CsvMessage (wraps; must never push Cancel/Save off the card), "Cancel" (outline), SaveLabel (primary). Max height 830.
9. Strip scroll memory: the host shows only the top dialog, so opening a NumberPad / process picker from a card replaces this view; the view saves `StepScroll.Offset.X` into `StripOffset` on real scrolls only (ignored when the extent or viewport changed, while restoring, or when detached) and restores it on attach (posted at Loaded priority). On `StepAdded(index)` (posted at Loaded priority) `CenterStep(index)` slides (Tween) the strip so the new card is centred; index 0 does not move.
**Configuration:** none
**Acceptance criteria:**
- Home "+ New" opens the editor as a modal with no steps; Save with no name shows "Enter a material name"; with a name and no steps "Add at least one step".
- Editing an existing program preloads it and "Update Program" replaces it (same Id).
- CSV export messages: ok "Saved to USB"; 9081 "No Disk-on-Key connected — connect one and try again"; other failure shows message.
- Added step is centred; choosing a process on a later step keeps the strip on that step; a long export message never pushes Cancel/Save off the card.
**Tests:** `EditorTests` (`Home_opens_the_editor_as_a_modal_with_no_steps`, `Editing_an_existing_program_preloads_it_and_updates_it`, `Csv_export_messages_follow_the_spec`, keypad tests), `EditorStripTests` (`Center_offset_puts_the_card_in_the_middle_of_what_is_visible`, `The_added_step_slides_into_the_middle_and_the_first_one_does_not_move`, `Choosing_a_process_on_a_later_step_keeps_the_strip_on_that_step`, `A_long_export_message_never_pushes_cancel_and_save_off_the_card`), `StepCardLayoutTests`.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/MaterialEditorDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/MaterialEditorDialogView.axaml(.cs)`, `src/SCureBox.Ui/ViewModels/Editor/EditorRules.cs`, `StepCardViewModel.cs`, `src/SCureBox.Ui/Resources/Strings.Editor.cs`, `HomeViewModel.cs` (OpenEditorAsync, DuplicateMaterial)

---

### UIDLG-14 — Import programs from CSV dialog
**Summary**
- **What it is for:** A dialog to import cure programs from CSV files on a USB drive.
- **Problem it solves:** Typing programs by hand is slow, and bad files must not create broken programs.
- **How we solve it:** The user picks CSV files one at a time. Each valid file becomes a program named after the file; bad files are listed with their errors.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/ImportCsvDialogViewModel.cs`, `Views/Dialogs/ImportCsvDialogView.axaml`
**Goal:** Pick CSV files from USB one at a time; each valid file becomes a user material immediately (name = file name without ".csv"); invalid files are listed with their parser/validator errors.
**Depends on:** UIDLG-01, UIDLG-06; Domain (`ProgramCsv.Parse`, `ProgramValidator.Validate`, `ProgramEstimator`); Native UI (`EditorRules.Normalize`); Application (`IMaterialStore`).
**Files to create:** `ImportCsvDialogViewModel.cs` with `public sealed record ImportResultRow(string FileName, bool Ok, IReadOnlyList<string> Errors)` (`Label` = "{file} — Added" / "{file} — Failed", `Failed => !Ok`), `public sealed record CsvSampleRow(string Step, string Process, string Temp, string Time, string Uv, string Mode)`, `public sealed partial class ImportCsvDialogViewModel : DialogViewModel<IReadOnlyList<Material>>` (ctor `(IMaterialStore materials, IDialogService dialogs, TimeProvider clock, ILogger<ImportCsvDialogViewModel> log)`); view.
**Public contract:** `CloseOnOverlayTap => false`; `DesignWidth => 1400`; `CancelResult => _added.ToList()`; `Title` "Import from CSV"; `Description` "Upload CSV files. Each file becomes a material in your list."; `SampleRows`; `ObservableCollection<ImportResultRow> Results`; `HasResults`; `CanFinish => Results.Count > 0 && Results.All(r => r.Ok)`; `Added`; `public ImportResultRow ImportFile(string fileName, string content)`; `public static string MapImportMessage(string message)`; commands `BrowseCommand`, `DoneCommand` (CanExecute `CanFinish`), `CancelDialogCommand`.
**Behaviour & rules:**
1. Browse: open UsbFileBrowser with Title "Select program CSV"; null → nothing; read the file; IO/permission error → failed row "Cannot read file: {message}"; else `ImportFile(fileName, content)`.
2. `ImportFile`: errors = parse errors; if steps parsed → add validator errors mapped by `MapImportMessage`; if no steps and no errors → "No valid steps found". Errors → failed row. Else material {Name = file name minus ".csv" (case-insensitive), Steps = `EditorRules.Normalize(steps)`, TotalDuration = `EstimateProgramMinutes`, CreatedAt = UTC now "O"} appended to user materials (`ReplaceUserMaterials`) and to `_added`; ok row.
3. `MapImportMessage`: contains "After an N2 purge, add a Cure or Bleaching step" → "Add a Cure or Bleaching step after the N₂ purge"; contains "Add a Cooling step after the Cure/Bleaching step that follows the N2 purge" → "Nitrogen must be vented — add a Cooling step after the N₂ purge"; otherwise replace "N2 purge" by "N₂ purge".
4. Done enabled only when at least one result and all ok; result = added materials. Cancel also returns the already added materials (they are already persisted). Home re-reads the list in both cases.
5. Layout: Title, Description; two columns: left — large dashed outline button (Folder icon, "Tap to browse or drag files here", "Unlimited files") and results list (max 300 high, green check / red X, Label, red error lines indented 36); right — "Example: how your CSV file should look" table with columns Step/Process/Temp/Time/UV%/Mode and sample rows (1 Drying 40 10; 2 Heating 60 5; 3 Nitrogen; 4 Cure 60 15 30; 5 Bleacher 60 10 40; 6 Cooling 30 medium) and footnote "Temp: 30-80°C (Drying 30-50°C, Cooling 30-75°C) · Time: 1-120 min (Bleaching up to 720) · UV: 10-100% · Mode: fast/medium/slow"; footer "Cancel" (outline), "Done" (primary).
**Configuration:** none
**Acceptance criteria:** a valid file adds a material and an "— Added" row; a bad file adds a "— Failed" row with errors and Done stays disabled; empty content gives "No valid steps found".
**Tests:** `EditorTests.Csv_import_adds_a_valid_file_and_reports_a_bad_one`.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/ImportCsvDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/ImportCsvDialogView.axaml`, `src/SCureBox.Ui/Resources/Strings.Editor.cs` (Import), `src/SCureBox.Domain/Programs/ProgramCsv.cs`, `ProgramValidator.cs`

---

### UIDLG-15 — Static IP configuration dialog
**Summary**
- **What it is for:** A form to set a fixed (static) network address for the machine.
- **Problem it solves:** Some sites need a fixed IP address, and a wrong address could cut the machine off the network.
- **How we solve it:** The form has fields for IP, Gateway, Subnet and DNS with a built-in number keypad. Apply works only when IP and Gateway are valid addresses.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/StaticIpDialogViewModel.cs`, `Views/Dialogs/StaticIpDialogView.axaml`
**Goal:** Enter IP, Gateway (both required), Subnet and DNS with an on-dialog numeric keypad; Apply only when IP and Gateway are valid dotted quads.
**Depends on:** UIDLG-01; Native UI (Network page); Application-Platform (`INetworkService.SetStatic`).
**Files to create:** `StaticIpDialogViewModel.cs` with `public sealed record StaticIpConfig(string Ip, string Gateway, string Subnet, string Dns);`, `public enum IpField { Ip, Gateway, Subnet, Dns }`, `public sealed partial class StaticIpDialogViewModel : DialogViewModel<StaticIpConfig?>`; view.
**Public contract:** `public static readonly Regex DottedQuad = ^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$`; `CloseOnOverlayTap => false`; `DesignWidth => 900`; `CancelResult => null`; `Title` "Static IP Configuration"; `[ObservableProperty]` `string Ip = ""`, `string Gateway = ""`, `string Subnet = "255.255.255.0"`, `string Dns = "8.8.8.8"`, `IpField Selected = Ip`; `IpSelected/GatewaySelected/SubnetSelected/DnsSelected`; `IpDisplay` (empty → "192.168.1.100"), `GatewayDisplay` (→ "192.168.1.1"), `SubnetDisplay` (→ "255.255.255.0"), `DnsDisplay` (→ "8.8.8.8"); `IpEmpty/GatewayEmpty/SubnetEmpty/DnsEmpty`; `IsValid => IsQuad(Ip) && IsQuad(Gateway)`; `public static bool IsQuad(string s)` (regex and each part ≤ 255); `Init(string ip, string gateway)` ("—" → ""); commands `SelectCommand(string field)` (case-insensitive enum parse), `KeyCommand(string k)`, `ClearFieldCommand`, `ApplyCommand` (CanExecute `IsValid`), `CancelDialogCommand`.
**Behaviour & rules:**
1. `Key("⌫")` removes the last char of the selected field; `Key(".")` appends "." only if the field is non-empty, does not end with ".", and has fewer than 3 dots; any other key appends while the field is shorter than 15 chars.
2. Apply → `Close(new StaticIpConfig(Ip, Gateway, Subnet empty ? "255.255.255.0" : Subnet, Dns empty ? "8.8.8.8" : Dns))`.
3. Network page: `Init(Ip, Gateway)` with current values; non-null result → optimistic update (StaticMode, Ip, Gateway, ConnectionName "static-eth0") then `SetStatic(false, ip, gateway, subnet, dns)`; refusal → warning log + alert (`r.Code ?? ErrorCodes.NetworkError`).
4. Layout: left column — Title; labels "IP Address *", "Gateway *", "Subnet Mask", "DNS Server" each above a mono field button (selected = primary border, empty = grey placeholder text); Cancel (outline) / Apply (primary). Right column 380 wide: keypad 1-9, ".", 0, ⌫ (red).
**Configuration:** none
**Acceptance criteria:** 256 in any octet or fewer than 4 octets → Apply disabled; valid IP+Gateway → Apply enabled and the network card shows the new values; empty Subnet/DNS fall back to defaults.
**Tests:** `NetworkTests.Static_ip_validation_rejects_bad_quads_and_apply_updates_the_card`.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/StaticIpDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/StaticIpDialogView.axaml`, `src/SCureBox.Ui/ViewModels/Pages/NetworkViewModel.cs`, `src/SCureBox.Ui/Resources/Strings.Settings.cs` (Network)

---

### UIDLG-16 — Software update dialog
**Summary**
- **What it is for:** The dialog that installs a software update from a USB drive.
- **Problem it solves:** Updates must come from a checked package, and the user must not close the window in the middle of installing.
- **How we solve it:** It shows four steps: find the USB, find the package, check its SHA-256 fingerprint, install. Closing is blocked while it runs. Then it offers Restart Now, or Retry on error.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/SoftwareUpdateDialogViewModel.cs`, `Views/Dialogs/SoftwareUpdateDialogView.axaml`
**Goal:** Install a `.scu` update from USB: idle plan → four running steps (find USB, find package, verify SHA-256, install) → success ("Restart Now" returns true) or error (Retry). Closing is blocked while running.
**Depends on:** UIDLG-01; Application-Platform (`IUpdateService`: `FindPackage`, `Manifest`, `RunUpdate`; DTOs `UpdatePackageDto`, `UpdateManifestDto`, `UpdateResultDto`); Native UI (Settings, Restart page).
**Files to create:** `SoftwareUpdateDialogViewModel.cs` with `public enum UpdateStepState { Pending, Running, Ok, Error }`, `public sealed partial class UpdateStepViewModel : ObservableObject` (`Label`, `[ObservableProperty] State`, `IsRunning/IsOk/IsError/IsPending`), `public sealed partial class SoftwareUpdateDialogViewModel : DialogViewModel<bool>` (ctor `(IUpdateService update, ILogger<SoftwareUpdateDialogViewModel> log)`); view.
**Public contract:** `public static readonly TimeSpan FindUsbDelay = 700 ms`; `CloseOnOverlayTap => false`; `DesignWidth => 820`; `CancelResult => false`; `Title` "Software Update"; `Intro` "Insert a USB drive with a .scu update file, then press Update."; `WillDo` "The update will:"; `Plan` ["1. Find the update file on USB", "2. Verify integrity (SHA-256)", "3. Back up current version", "4. Install new version", "5. Restart services"]; `ObservableCollection<UpdateStepViewModel> Steps`; `[ObservableProperty]` `bool IsIdle = true`, `IsRunning`, `IsSuccess`, `IsError`, `string VersionText`, `string ErrorMessage`; `SuccessTitle` "Update successful!", `WillRestart` "The system will restart.", `FailedTitle` "Update failed", `PreviousRestored` "The previous version was restored."; `PrimaryLabel` (IsError ? "Retry" : "Update"); `CancelLabel` (IsSuccess ? "Restart Now" : "Cancel"); `ShowPrimary => IsIdle || IsError`; `CanClose => !IsRunning`; `override Cancel()` (no-op while running, else `Close(IsSuccess)`); `CancelDialogCommand` and `RunCommand` (both CanExecute `CanClose`).
**Behaviour & rules:**
1. Run: IsIdle=false, IsError=false, IsSuccess=false, IsRunning=true; Steps = "Finding USB drive...", "Looking for update package...", "Verifying integrity (SHA-256)...", "Installing update...".
2. Step 1: Running, wait 700 ms, Ok (cosmetic). Step 2: `Task.Run(FindPackage)`; not Ok → fail step with "No update package found ({message ?? code ?? "?"})". Step 3: `Task.Run(Manifest)`; not Ok → fail with message or "No update package found ({code ?? "?"})"; Sha256 blank or length ≠ 64 → "Missing or malformed checksum — update rejected". Step 4: `Task.Run(RunUpdate)`; not Ok → message contains "checksum" or "hash" (case-insensitive) → "Checksum mismatch — the package is corrupt or has been tampered with", else the message. Success → VersionText "Version: {result.Version ?? manifest.Version ?? "?"}", IsSuccess.
3. Exception → warning log; the running step (or install) fails with the exception message. Finally IsRunning=false.
4. Fail = step State Error, ErrorMessage, IsError (Primary becomes Retry; Retry runs again from scratch).
5. Settings: result true → navigate to Restart page with the update parameter and reboot ("Installing the update and restarting…").
6. Layout: Upload icon + Title; idle — Intro + plan box; running/finished — step list (Loader / green CheckCircle / red XCircle / grey dot, label muted while pending); green success box (title, version, will restart); red error box (title, message, previous restored); buttons CancelLabel (outline), primary PrimaryLabel with Refresh icon (visible when ShowPrimary).
7. Error codes from `IUpdateService.FindPackage`: 9081 no USB, 9087 no package, 9086 other (shown via the message/code text).
**Configuration:** none
**Acceptance criteria:** happy path ends in success with "Restart Now" resolving true; missing package fails step 2; malformed sha fails step 3; checksum failure message is mapped; Cancel is ignored while running; Retry is shown after an error.
**Tests:** OPEN QUESTION: no dedicated test class for this dialog was found in `tests/SCureBox.Ui.Tests` (1.0.152); implement tests with a fake `IUpdateService` covering each failure step.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/SoftwareUpdateDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/SoftwareUpdateDialogView.axaml`, `src/SCureBox.Application/Platform/IUpdateService.cs`, `UpdatePackageDto.cs`, `UpdateManifestDto.cs`, `UpdateResultDto.cs`, `SettingsViewModel.cs` (UpdateSoftware)

---

### UIDLG-17 — Versions dialog
**Summary**
- **What it is for:** A window that shows the machine's software and system versions and the version history.
- **Problem it solves:** Support and engineers need to see exactly what software is installed and what changed.
- **How we solve it:** It shows live software, build, OS, kernel, runtime and last-boot details, plus the history read from the versions file.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/VersionsDialogViewModel.cs`, `Views/Dialogs/VersionsDialogView.axaml`
**Goal:** Show the live software/build/OS/kernel/runtime/last-boot block and the version history parsed from `config/versions.json`.
**Depends on:** UIDLG-01; Application-Platform (`ISystemService.Version()`, `VersionInfoDto`); Application (`DataOptions.ConfigDir`).
**Files to create:** `VersionsDialogViewModel.cs` with `public sealed record VersionEntry(string Version, string Date, IReadOnlyList<string> Notes)` (`Tag => "v{Version}"`, `Bullets => "· {note}"`), `public sealed partial class VersionsDialogViewModel : DialogViewModel<bool>` (ctor `(ISystemService system, DataOptions data, ILogger<VersionsDialogViewModel> log)`); view.
**Public contract:** `CloseOnOverlayTap => true`; `DesignWidth => 900`; `CancelResult => false`; `Title` "Versions"; `Software`, `Build`, `Os`, `Kernel`, `Runtime`, `LastBoot`, `History`, `HasHistory`; `CloseDialogCommand` → true; `public static IReadOnlyList<VersionEntry> ParseHistory(string json)`.
**Behaviour & rules:**
1. Constructor: `system.Version()` (exception → warning log + empty `VersionInfoDto`, AppVersion "unknown"); Software = AppVersion; Build = GitCommit null ? "—" : "{commit} · {date ?? "—"}"; Os/Kernel/LastBoot or "—"; Runtime = Runtime ?? Python ?? "—".
2. History from `Path.Combine(ConfigDir, "versions.json")` if it exists; JSON `{ "history": [ { "version", "date", "notes": [] } ] }` (case-insensitive), missing fields → "" / empty list; IO/JSON/permission errors → warning log, empty list.
3. Layout: Title (h2) + X close icon; key/value block (Software bold; Build, Kernel, Last Boot mono); "VERSION HISTORY" label; "No version history available." when empty; else scroll (max 480) of cards: Tag icon + "v{version}" + date (mono) + bullet notes.
**Configuration:** reads `<ConfigDir>/versions.json`.
**Acceptance criteria:** the dialog shows the app version and the history entries; a missing file shows the empty text.
**Tests:** `SettingsTests.Versions_dialog_shows_the_app_version_and_the_history`.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/VersionsDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/VersionsDialogView.axaml`, `src/SCureBox.Application/Platform/VersionInfoDto.cs`

---

### UIDLG-18 — Cybersecurity compliance dialog
**Summary**
- **What it is for:** An information window about the machine's cybersecurity compliance.
- **Problem it solves:** Users and auditors need to see which security standards apply and what protection is in place or planned.
- **How we solve it:** A fixed panel lists the standards (CRA, EN 18031, EN 40000), the security controls marked Active or Planned, and the SRS requirements with their dates.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/ComplianceDialogViewModel.cs`, `Views/Dialogs/ComplianceDialogView.axaml`
**Goal:** Static information panel listing the standards (CRA, EN 18031, EN 40000), code-level controls (ACTIVE/PLANNED) and the SRS §22 requirements with effective dates.
**Depends on:** UIDLG-01; Native UI (Settings).
**Files to create:** `ComplianceDialogViewModel.cs` — `public sealed partial class ComplianceDialogViewModel : DialogViewModel<bool>` with nested `public sealed record StandardRow(string Id, string Name)`, `public sealed record ControlRow(string Label, bool Active, string Detail, string Requirements)` (`Status` "ACTIVE"/"PLANNED", `Planned`), `public sealed record RequirementRow(string Id, string Text, string Effective)` (`HasEffective`); view.
**Public contract:** `CloseOnOverlayTap => true`; `DesignWidth => 1040`; `CancelResult => false`; `Title` "Cybersecurity Compliance"; `Footer`; `Standards`, `Controls`, `Requirements`; `CloseDialogCommand` → true.
**Behaviour & rules:**
1. Rows come from `Strings.Compliance.StandardList`, `ControlList` (requirements joined with two spaces), `RequirementList` (Effective = "effective {dd MMM yyyy}" (invariant) when the ISO "yyyy-MM-dd" parses, else "").
2. Data (exact): standards CRA / EN 18031 / EN 40000; controls update-integrity (active, REQ-CRA-05/06), sbom (active, REQ-CRA-07), network-access-control (planned, REQ-CRA-05), vuln-handling (planned, REQ-CRA-03); requirements REQ-CRA-01..08 with REQ-CRA-03 effective 2026-11-11, REQ-CRA-04 and -08 effective 2027-12-11 (full texts in `Strings.Settings.cs` Compliance).
3. Layout: green ShieldCheck + Title + X; scroll (max 700): "Standards" section (Id 180 px column + name), "Controls in software" cards (green check or clock icon, label, detail, requirement ids mono primary, ACTIVE green pill / PLANNED grey pill), "Requirements (SRS §22)" rows, footer; outline "Close".
**Configuration:** none
**Acceptance criteria:** the view-model data matches the spec lists (counts, statuses, formatted dates "effective 11 Nov 2026").
**Tests:** `SettingsTests.Compliance_data_matches_the_spec`.
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/ComplianceDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/ComplianceDialogView.axaml`, `src/SCureBox.Ui/Resources/Strings.Settings.cs` (Compliance)

---

### UIDLG-19 — Origin sign-in dialog (embedded web page or in-window browser)
**Summary**
- **What it is for:** A window where the operator signs in to the Origin website to link the machine to their organization.
- **Problem it solves:** The machine needs the user's Origin organization, but must not keep any sign-in details.
- **How we solve it:** The real Origin site is shown inside the dialog as live pictures; taps and drags are passed to it, and text fields open the keyboard. Only the organization is returned; nothing else is saved.

**Project / folder:** `src/SCureBox.Ui/SCureBox.Ui.csproj` — `ViewModels/Dialogs/OriginSignInDialogViewModel.cs`, `Views/Dialogs/OriginSignInDialogView.axaml(.cs)`
**Goal:** Let the operator sign in to the real Origin site (app.origin.io: email / Google / Microsoft) inside the dialog — the page is streamed as JPEG frames, finger taps/drags are forwarded, tapping a text field opens the docked keyboard — and return only the organization. Nothing about the sign-in is stored.
**Depends on:** UIDLG-01, UIDLG-03; Native UI service `OriginBrowserSignIn` (`IOriginBrowserSignIn`, `IOriginSurface`, `IOriginInput`, `OriginField`, `OriginPhase`, `OriginOrganization`, `OriginSignInResult`; headless browser, `config/origin.json`); Setup and Settings pages.
**Files to create:** `OriginSignInDialogViewModel.cs` with `public enum PagePointer { Down, Move, Up }` and `public sealed partial class OriginSignInDialogViewModel : DialogViewModel<OriginOrganization?>, IOriginSurface` (ctor `(IOriginBrowserSignIn origin, IDialogService dialogs)`); `OriginSignInDialogView.axaml(.cs)`.
**Public contract:** `CloseOnOverlayTap => false`; `DesignWidth => origin.Embedded ? 1440 : 820`; `CancelResult => null`; `Title` "Sign in to Origin"; `PageWidth => 1360`, `PageHeight => 760` (`OriginBrowserSignIn.ViewWidth/ViewHeight`); `[ObservableProperty]` `Bitmap? Frame`, `bool Busy = true`, `string? Error`, `bool Ready`; `HasError`, `ShowPage => Frame != null && !HasError`, `ShowStatus => !ShowPage`, `InWindow => !origin.Embedded`, `Status` (HasError ? Error : InWindow && Ready ? Strings.Origin.InWindow : "Opening the Origin website..."); `public Task RunAsync()`; `RetryCommand` (CanExecute `HasError`); `CancelDialogCommand`; `public void Pointer(PagePointer phase, double fx, double fy)`; explicit `IOriginSurface` members `Attached`, `Phase`, `ShowFrame`, `EditAsync`.
**Behaviour & rules:**
1. `OnShown` starts `RunAsync()`: Busy=true, Error=null, Ready=false; `await origin.SignInAsync(this, cts.Token)`; if cancelled → return; Organization → `Close(org)`; Error null (page went away) → `Cancel()`; else Busy=false, Error = r.Error (operator texts from the service: "Sign-in took too long - try again", "Origin sign-in failed - try again", "No web browser found on this machine", "Origin sign-in is not set up on this machine (config/origin.json)").
2. `Retry` (only with an error) runs `RunAsync` again. `CancelDialog` cancels the CTS and `Cancel()` → null.
3. Surface callbacks (background threads): `Attached(input)` stores the input; `Phase(p)` posts `Ready = p == Ready` to the UI thread; `ShowFrame(jpeg)` decodes a `Bitmap` (torn frame → ignored), posts swap of `Frame` and disposes the old one; `EditAsync(field)` posts to the UI thread and shows the keyboard with `Text = field.Value`, `Masked = field.IsPassword`, `Docked = true`, returning the keyboard text.
4. `Pointer`: NaN coordinates (capture lost) → forget the press. Down → remember start/last, not dragged. Move with a press: if not yet dragged and |dx|+|dy| < 0.012 (TapSlop, fractions of the picture) → ignore; else dragged, `input.Scroll(fx, fy, (last.Y - fy) * 760)`, last = current. Up with a press: if not dragged → `input.Tap(down.X, down.Y)`; clear.
5. View code-behind: `PageImage` pointer pressed/moved (only with left button pressed)/released send positions as fractions of the image bounds (event handled); `PointerCaptureLost` sends `Up` with NaN.
6. Layout: header — 64 px primary-dim circle Globe icon; Title (h2) + "Only the organization is taken from your account. Nothing about your sign-in is stored on this machine." (xxs muted); "Try Again" primary (visible with error); "Cancel" outline. In-window mode: secondary box with Status, steps "1  Sign in at the Origin window", "2  Wait until your models page appears", "3  The window closes and the organization is linked", indeterminate progress bar (hidden on error), error text (red). Embedded mode: 1360x760 rounded clipped box with the page `Image` (Stretch Fill, visible when ShowPage) or the Status text centred.
7. Results: Settings → `SetOrganization(org.Id)`, clears org error; Setup → OrganizationId = org.Id, file text "from Origin account {email ?? name ?? ""}".
8. The screensaver does not interrupt it (dialogs suppress idle, UIDLG-01).
**Configuration:** `config/origin.json` (consumed by the `OriginBrowserSignIn` service, not by the dialog).
**Acceptance criteria:**
- The dialog waits and closes with the organization; an error shows "Try Again" and retry works; a vanished page cancels (null).
- In-window mode says where to sign in and is 820 wide.
- A short press taps the page; a drag scrolls it.
- Tapping a field opens the docked keyboard and its text goes into the field.
- Settings and Setup sign-in link the organization.
**Tests:** `OriginSignInTests` (`Dialog_waits_then_closes_with_the_organization`, `Dialog_shows_an_error_and_can_try_again_and_a_vanished_page_cancels_it`, `In_window_mode_the_dialog_says_where_to_sign_in_and_is_narrow`, `A_short_press_taps_the_page_and_a_drag_scrolls_it`, `Tapping_a_field_on_the_page_opens_the_keyboard_and_the_text_goes_in`, `Settings_sign_in_links_the_organization`, `Setup_sign_in_shows_the_account_and_completes_setup`, plus service-level tests).
**Reference (source):** `src/SCureBox.Ui/ViewModels/Dialogs/OriginSignInDialogViewModel.cs`, `src/SCureBox.Ui/Views/Dialogs/OriginSignInDialogView.axaml(.cs)`, `src/SCureBox.Ui/Services/OriginBrowserSignIn.cs`, `src/SCureBox.Ui/Resources/Strings.Origin.cs`, `SettingsViewModel.cs` (SignInOrigin), `SetupViewModel.cs` (SignInOrigin)
