/** #52 / D-058 §2.3 — secondary disclosure. A single fixed top-strip chip can be cropped out of
 * a screenshot focused on one panel; this can't, by construction: a full-bleed, diagonal,
 * repeating "MOCK DATA" field painted above every panel (fixed, `--bd-z-presentation`, above
 * `--bd-z-alert`) at low opacity, `pointer-events: none` so it never intercepts a click.
 * Recoloured/rotated variant of the same 135°, 38px-pitch hazard-stripe construction
 * `global.css`'s page background already uses (`repeating-linear-gradient(135deg, ...)`),
 * per D-058, plus the literal repeated words the design record adds beyond that base texture.
 *
 * Real DOM text nodes, not a background image — screen-reader users get nothing extra to wade
 * through (`aria-hidden`, the chip above already carries the accessible disclosure), and a
 * screenshot rasterizes text exactly as reliably as an image. `ROWS`/`COLS` are sized generously
 * enough that the rotated field still fully covers a 1440×900+ viewport with margin, so cropping
 * to any single panel never lands on a gap. Never mounted outside a `command-center:presentation`
 * build (`PresentationMissionCommandCenter`) and never rendered unless
 * `deriveConfirmedMock` (`lib/presentation/provenance.ts`) is true for the current mission — see
 * that component.
 */
const ROWS = 16;
const COLS = 7;

export function MockDataWatermark() {
  return (
    <div className="bd-mock-watermark" aria-hidden="true">
      <div className="bd-mock-watermark__field">
        {Array.from({ length: ROWS }, (_, row) => (
          <div className="bd-mock-watermark__row" key={row}>
            {Array.from({ length: COLS }, (_, col) => (
              <span key={col}>MOCK DATA</span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
