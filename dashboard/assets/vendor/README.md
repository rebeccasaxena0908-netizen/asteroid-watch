# Vendored libraries

Local copies so the dashboard works **offline** (for example during a demo without Wi-Fi). Nothing is loaded from a CDN at runtime.

Every file was downloaded from jsdelivr at the exact version below and checked against the SHA-256 hash jsdelivr publishes for that package version (`https://data.jsdelivr.com/v1/packages/npm/<package>@<version>?structure=flat`). `fonts/fonts.css` is our own file, built from the fontsource CSS, with only the latin and latin-ext subsets.

| Package | Source file | Local file | Bytes | SHA-256 | Licence |
|---|---|---|---|---|---|
| `three@0.160.0` | `/build/three.module.min.js` | `three/three.module.min.js` | 670,681 | `3e690ac7d180b0aa…` | MIT (three/LICENSE) |
| `three@0.160.0` | `/LICENSE` | `three/LICENSE` | 1,081 | `852e0e8699169bf9…` | MIT (three/LICENSE) |
| `chart.js@4.4.1` | `/LICENSE.md` | `chartjs/LICENSE.md` | 1,093 | `5a0877ad6d818529…` | MIT (chartjs/LICENSE.md) |
| `@fontsource/inter@5.0.18` | `/LICENSE` | `fonts/inter/LICENSE` | 4,375 | `426ef06df3fa0af4…` | SIL OFL 1.1 (fonts/inter/LICENSE) |
| `@fontsource/inter@5.0.18` | `/files/inter-latin-400-normal.woff2` | `fonts/inter/inter-latin-400-normal.woff2` | 21,564 | `2301bb030a2bcaa9…` | SIL OFL 1.1 (fonts/inter/LICENSE) |
| `@fontsource/inter@5.0.18` | `/files/inter-latin-600-normal.woff2` | `fonts/inter/inter-latin-600-normal.woff2` | 22,820 | `3022fadde78fd30c…` | SIL OFL 1.1 (fonts/inter/LICENSE) |
| `@fontsource/inter@5.0.18` | `/files/inter-latin-ext-400-normal.woff2` | `fonts/inter/inter-latin-ext-400-normal.woff2` | 29,268 | `56d25f402cc61fdc…` | SIL OFL 1.1 (fonts/inter/LICENSE) |
| `@fontsource/inter@5.0.18` | `/files/inter-latin-ext-600-normal.woff2` | `fonts/inter/inter-latin-ext-600-normal.woff2` | 32,548 | `5f70855945ba172e…` | SIL OFL 1.1 (fonts/inter/LICENSE) |
| `@fontsource/space-grotesk@5.0.18` | `/LICENSE` | `fonts/space-grotesk/LICENSE` | 4,401 | `18a4de52385f6b98…` | SIL OFL 1.1 (fonts/space-grotesk/LICENSE) |
| `@fontsource/space-grotesk@5.0.18` | `/files/space-grotesk-latin-500-normal.woff2` | `fonts/space-grotesk/space-grotesk-latin-500-normal.woff2` | 13,320 | `f674168ce1553b06…` | SIL OFL 1.1 (fonts/space-grotesk/LICENSE) |
| `@fontsource/space-grotesk@5.0.18` | `/files/space-grotesk-latin-600-normal.woff2` | `fonts/space-grotesk/space-grotesk-latin-600-normal.woff2` | 13,212 | `e7c4b716fad7c631…` | SIL OFL 1.1 (fonts/space-grotesk/LICENSE) |
| `@fontsource/space-grotesk@5.0.18` | `/files/space-grotesk-latin-ext-500-normal.woff2` | `fonts/space-grotesk/space-grotesk-latin-ext-500-normal.woff2` | 11,788 | `ee4949b767abc01e…` | SIL OFL 1.1 (fonts/space-grotesk/LICENSE) |
| `@fontsource/space-grotesk@5.0.18` | `/files/space-grotesk-latin-ext-600-normal.woff2` | `fonts/space-grotesk/space-grotesk-latin-ext-600-normal.woff2` | 11,920 | `1a9d4744033f4dc7…` | SIL OFL 1.1 (fonts/space-grotesk/LICENSE) |
| `chart.js@4.4.1` | `/dist/chart.umd.js` | `chartjs/chart.umd.js` | 205,125 | `74401d738dd3e03e…` | MIT (chartjs/LICENSE.md) |

To update: download the new version from `https://cdn.jsdelivr.net/npm/<package>@<version>/<file>`, verify its hash against the jsdelivr data API, replace the file here and update the version in `dashboard/index.php` and this table.
