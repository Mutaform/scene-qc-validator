# -*- coding: utf-8 -*-
"""Сводка проверки в виде HTML-страницы, открываемой в браузере.

Страница та же, что в ARDENA Tools (ardena_report.py): шапка с логотипом, плитки,
«Что исправить», таблица и карточки - на тех же местах и теми же словами, чтобы
проверяющий двух инструментов видел одно и то же. Различаются только строки с
находками: там ассеты движка, здесь объекты сцены Blender.

Зачем не панель. Панель показывает результаты построчно и годится, пока их
десяток. Приёмка сета - это таблица на полсотни строк: что сломано, у скольких
объектов, что из этого чинится кнопкой. В боковой панели Blender такое не
помещается читаемо, сколько его ни ужимай.

Страница самодостаточна: стили внутри, ни одного внешнего файла, работает без
интернета. Её можно переслать художнику как есть - это готовое письмо «вот что
не так с ассетами». Кнопки на пересланной копии выключены: они работают, пока
открыт Blender, который её написал (см. live.py).

Порядок на странице - от главного к подробностям:
  1. плитки с итогом и список «Что исправить»: каждая находка один раз, с
     перечнем объектов и строкой «чем чинится»;
  2. таблица объектов - по строке на объект, вердикт виден без чтения;
  3. карточки по объектам со всеми находками.
"""

import datetime
import html
import json
import os

from . import explain
from . import facts as facts_mod

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

VERDICT_OK = "ПРИНЯТ"
VERDICT_BAD = "ОТКЛОНЁН"

# Логотип студии вшит прямо в страницу: она должна оставаться ОДНИМ файлом,
# который можно переслать художнику, без папки с картинками рядом.
LOGO = '<svg class="logo" viewBox="0 0 3071 582" xmlns="http://www.w3.org/2000/svg" aria-label="Mutaform"><path fill="currentColor" d="M109.731 549.769H19.4603V478.431H109.731V483.661H25.6318V510.857H107.639V515.564H25.6318V544.539H109.731V549.769ZM124.64 478.431H134.159L173.698 510.23L213.132 478.431H222.442L178.509 513.891L223.383 549.769H213.551L173.489 517.343L133.322 549.769H123.803L168.572 513.786L124.64 478.431ZM278.106 483.87H234.487V478.431H327.792V483.87H284.277V549.769H278.106V483.87ZM433.692 549.769H343.421V478.431H433.692V483.661H349.593V510.857H431.6V515.564H349.593V544.539H433.692V549.769ZM458.329 549.769H452.157V478.431H518.474C535.838 478.431 543.997 485.439 543.997 500.502C543.997 515.146 536.361 522.364 519.207 522.573H508.746L515.65 527.907L541.8 549.769H533.641L501.424 522.782H458.329V549.769ZM458.329 483.87V517.657H518.579C532.177 517.657 537.721 512.74 537.721 500.816C537.721 488.787 532.177 483.87 518.579 483.87H458.329ZM569.108 549.769H562.936V478.431H570.258L652.475 543.179V478.431H658.646V549.769H651.324L569.108 484.812V549.769ZM774.859 549.769L761.679 531.568H690.969L677.684 549.769H670.153L722.349 478.431H730.299L782.39 549.769H774.859ZM694.525 526.652H758.018L726.324 482.929L694.525 526.652ZM800.064 544.33H883.64V549.769H793.892V478.431H800.064V544.33ZM1000.8 549.769H941.596V478.431H1000.8C1030.19 478.431 1043.16 488.787 1043.16 513.995C1043.16 539.204 1030.19 549.769 1000.8 549.769ZM947.768 483.87V544.33H1000.49C1027.16 544.33 1036.89 535.229 1036.89 513.995C1036.89 492.552 1027.16 483.87 1000.49 483.87H947.768ZM1151.02 549.769H1060.75V478.431H1151.02V483.661H1066.92V510.857H1148.93V515.564H1066.92V544.539H1151.02V549.769ZM1214.15 549.769L1163 478.431H1170.53L1218.23 544.644L1265.93 478.431H1273.36L1222.1 549.769H1214.15ZM1376.77 549.769H1286.5V478.431H1376.77V483.661H1292.67V510.857H1374.68V515.564H1292.67V544.539H1376.77V549.769ZM1401.41 544.33H1484.98V549.769H1395.23V478.431H1401.41V544.33ZM1547.59 550.92C1510.77 550.92 1493.09 539.937 1493.09 514.1C1493.09 488.264 1510.77 477.281 1547.59 477.281C1584.41 477.281 1602.09 488.264 1602.09 514.1C1602.09 539.937 1584.41 550.92 1547.59 550.92ZM1547.59 545.271C1583.05 545.271 1595.81 535.125 1595.81 514.1C1595.81 493.075 1583.05 482.929 1547.59 482.929C1512.13 482.929 1499.26 493.075 1499.26 514.1C1499.26 535.125 1512.13 545.271 1547.59 545.271ZM1619.65 549.769V478.431H1686.91C1704.27 478.431 1712.43 485.23 1712.43 499.77C1712.43 514.518 1704.27 521.422 1686.91 521.422H1625.82V549.769H1619.65ZM1686.91 483.87H1625.82V515.983H1686.91C1700.51 515.983 1706.16 511.38 1706.16 499.979C1706.16 488.473 1700.51 483.87 1686.91 483.87ZM1733.74 549.769H1727.57V478.431H1735.21L1790.44 544.539L1845.56 478.431H1853.09V549.769H1846.92V485.753L1793.36 549.769H1787.3L1733.74 485.753V549.769ZM1963.04 549.769H1872.77V478.431H1963.04V483.661H1878.95V510.857H1960.95V515.564H1878.95V544.539H1963.04V549.769ZM1987.68 549.769H1981.51V478.431H1988.83L2071.05 543.179V478.431H2077.22V549.769H2069.9L1987.68 484.812V549.769ZM2136.43 483.87H2092.81V478.431H2186.11V483.87H2142.6V549.769H2136.43V483.87ZM2249.38 514.1C2249.38 535.02 2260.37 545.271 2291.75 545.271C2309.01 545.271 2327.21 541.819 2339.03 539.1L2340.28 544.434C2327.1 547.886 2308.17 550.815 2291.64 550.815C2258.69 550.815 2243.21 539.623 2243.21 514.1C2243.21 488.577 2258.69 477.385 2291.64 477.385C2308.17 477.385 2327.1 480.419 2340.28 483.766L2339.03 489.205C2327.21 486.381 2309.01 482.929 2291.75 482.929C2260.37 482.929 2249.38 493.284 2249.38 514.1ZM2407.16 550.92C2370.34 550.92 2352.66 539.937 2352.66 514.1C2352.66 488.264 2370.34 477.281 2407.16 477.281C2443.98 477.281 2461.66 488.264 2461.66 514.1C2461.66 539.937 2443.98 550.92 2407.16 550.92ZM2407.16 545.271C2442.62 545.271 2455.38 535.125 2455.38 514.1C2455.38 493.075 2442.62 482.929 2407.16 482.929C2371.7 482.929 2358.84 493.075 2358.84 514.1C2358.84 535.125 2371.7 545.271 2407.16 545.271ZM2485.39 549.769H2479.22V478.431H2486.86L2542.09 544.539L2597.21 478.431H2604.74V549.769H2598.57V485.753L2545.02 549.769H2538.95L2485.39 485.753V549.769ZM2624.43 549.769V478.431H2691.69C2709.05 478.431 2717.21 485.23 2717.21 499.77C2717.21 514.518 2709.05 521.422 2691.69 521.422H2630.6V549.769H2624.43ZM2691.69 483.87H2630.6V515.983H2691.69C2705.28 515.983 2710.93 511.38 2710.93 499.979C2710.93 488.473 2705.28 483.87 2691.69 483.87ZM2820.31 549.769L2807.13 531.568H2736.42L2723.14 549.769H2715.61L2767.8 478.431H2775.75L2827.84 549.769H2820.31ZM2739.98 526.652H2803.47L2771.78 482.929L2739.98 526.652ZM2845.52 549.769H2839.35V478.431H2846.67L2928.88 543.179V478.431H2935.06V549.769H2927.73L2845.52 484.812V549.769ZM2994.26 520.272L2946.35 478.431H2954.83L2997.4 515.251L3040.08 478.431H3048.34L3000.43 520.272V549.769H2994.26V520.272Z"/><path fill="currentColor" d="M102.746 336H13.2575V109.959H121.969L238.635 262.752L355.301 109.959H462.024V336H372.536V216.351L283.048 336H192.234L102.746 216.02V336ZM733.668 215.025V109.959H823.157V234.58C823.157 310.811 755.875 339.977 654.123 339.977C552.372 339.977 485.09 310.811 485.09 234.58V109.959H574.578V215.025C574.578 253.803 597.448 263.747 654.123 263.747C710.799 263.747 733.668 253.803 733.668 215.025ZM968.684 186.19H836.44V109.959H1190.08V186.19H1058.17V336H968.684V186.19ZM1422.34 336L1400.8 298.548H1262.59L1241.05 336H1133.66L1272.53 109.959H1392.18L1531.05 336H1422.34ZM1297.72 237.232H1365.67L1331.86 178.567L1297.72 237.232ZM1627.23 336H1537.74V109.959H1846.64V186.19H1627.23V204.088H1840.34V273.69H1627.23V336ZM2043.44 340.972C1907.88 340.972 1851.87 303.519 1851.87 222.98C1851.87 142.44 1907.88 104.988 2043.44 104.988C2179 104.988 2235.01 142.44 2235.01 222.98C2235.01 303.519 2179 340.972 2043.44 340.972ZM2043.44 264.741C2123.98 264.741 2143.87 256.124 2143.87 222.98C2143.87 189.836 2123.98 181.219 2043.44 181.219C1962.9 181.219 1941.36 189.836 1941.36 222.98C1941.36 256.124 1962.9 264.741 2043.44 264.741ZM2344.48 336H2254.99V109.959H2488.99C2545 109.959 2589.75 128.189 2589.75 193.15C2589.75 244.523 2557.6 268.718 2509.87 274.021L2503.9 274.684L2519.81 282.97L2590.08 336H2478.38L2406.79 279.656H2344.48V336ZM2344.48 186.19V213.368H2479.05C2491.64 213.368 2496.94 210.054 2496.94 200.111C2496.94 188.51 2491.64 186.19 2479.05 186.19H2344.48ZM2697.93 336H2608.44V109.959H2717.15L2833.82 262.752L2950.48 109.959H3057.21V336H2967.72V216.351L2878.23 336H2787.42L2697.93 216.02V336Z"/></svg>'

CSS = """
:root{--bg:#1b1c20;--card:#242529;--line:#34353b;--txt:#e6e6e8;--dim:#9a9ba2;
      --gold:#C9B489;
      --err:#ff6b5e;--warn:#e8b23a;--ok:#5fc27e;--acc:#7aa2f7}
*{box-sizing:border-box}
body{margin:0;padding:26px 30px 34px;background:var(--bg);color:var(--txt);
     font:14px/1.55 "Segoe UI",system-ui,sans-serif}
.head{display:flex;align-items:center;gap:18px;padding:0 0 18px;
      border-bottom:1px solid var(--line);margin-bottom:22px}
.logo{height:26px;width:auto;color:var(--txt);flex:none}
.head .div{width:1px;height:26px;background:var(--line)}
h1{font-size:17px;font-weight:600;letter-spacing:.3px;margin:0;color:var(--txt)}
h1 span{color:var(--gold)}
.all{margin-left:auto;display:flex;align-items:center;gap:8px;font-size:13px;color:var(--dim);
     cursor:pointer;user-select:none}
.all input{width:16px;height:16px;margin:0;accent-color:var(--gold);cursor:pointer}
body.only-bad tr.clean,body.only-bad details.clean{display:none}
.sub{color:var(--dim);font-size:12px;margin:-14px 0 20px}
.sub b{color:var(--txt);font-weight:600}
.tiles{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:12px 18px;min-width:128px}
/* не «clean»: этим классом уже помечены карточки объектов без находок
   (body.only-bad details.clean), и display:flex ломал им вёрстку */
.allgood{display:flex;align-items:center;gap:10px;font-size:15px;font-weight:600;color:var(--ok)}
.allgood span{font-weight:400;color:var(--dim);font-size:13px}
/* Полоса прокрутки в общем тоне страницы: белая в тёмном отчёте - как дырка */
*{scrollbar-color:#3a3b42 var(--bg);scrollbar-width:thin}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:#3a3b42;border-radius:5px;border:2px solid var(--bg)}
::-webkit-scrollbar-thumb:hover{background:#4a4b55}
canvas.fx{position:fixed;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:50}
.tile.pulse{animation:pulse 1.3s ease-out}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(95,194,126,.55);border-color:var(--ok)}
                 100%{box-shadow:0 0 0 26px rgba(95,194,126,0);border-color:var(--line)}}
.tile.apart{margin-left:auto}
.tile.apart b{font-size:22px}
.tile b{display:block;font-size:26px;font-weight:600;line-height:1.15}
.tile span{color:var(--dim);font-size:12px}
.tile.ok b{color:var(--ok)} .tile.no b{color:var(--err)} .tile.w b{color:var(--warn)}
h2.sec{font-size:12px;letter-spacing:1px;color:var(--acc);margin:26px 0 10px;text-transform:uppercase}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:14px 20px;margin-bottom:12px}
.card .prob:first-child{margin-top:0}
.scroll{overflow-x:auto}
.who{color:var(--dim);font-size:12px;margin:1px 0 4px}
.fix{font-size:12px;margin:1px 0 6px;color:var(--dim)}
.fix b{font-weight:600}
.fix.auto{color:var(--ok)} .fix.manual b{color:var(--gold)} .fix.note{color:#7d7e86}
.fix.button b{color:var(--acc)}
.how{display:flex;gap:22px;flex-wrap:wrap;align-items:center;margin:0 0 12px;padding-bottom:10px;
     border-bottom:1px solid var(--line)}
.how .fix{margin:0;font-size:13px}
.how .grp{display:flex;gap:10px;align-items:center}
button.act{font:600 12px "Segoe UI",system-ui,sans-serif;color:#17181b;background:var(--gold);border:0;
           border-radius:4px;padding:5px 12px;cursor:pointer;margin-left:8px}
button.act:hover{filter:brightness(1.1)}
button.act:disabled{background:#3a3b41;color:#7d7e86;cursor:default;filter:none}
.how button.act{margin-left:0}
.live{font-size:12px;color:var(--dim);margin-left:auto}
.live.on{color:var(--ok)} .live.off{color:var(--warn)} .live.run{color:var(--acc)}
.note{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--ok);border-radius:6px;
      padding:10px 16px;margin:0 0 18px;font-size:13px}
.note.bad{border-left-color:var(--err)}
table.sum{border-collapse:collapse;width:100%}
table.sum th{font-size:11px;font-weight:600;color:var(--dim);text-align:left;padding:4px 12px 6px 0;
             border-bottom:1px solid var(--line);white-space:nowrap}
table.sum td{padding:4px 12px 4px 0;border-bottom:1px solid #2b2c31;white-space:nowrap;
             font:13px ui-monospace,Consolas,monospace}
table.sum td.n{font-family:"Segoe UI",sans-serif}
table.sum td.ok,span.ok{color:var(--ok)} table.sum td.warn,span.warn{color:var(--warn)}
table.sum td.bad,span.bad{color:var(--err)} table.sum td.dim{color:var(--dim)}
.asset{background:var(--card);border:1px solid var(--line);border-radius:6px;
       padding:18px 20px;margin-bottom:18px}
.top{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:4px}
summary{cursor:pointer;list-style:none;user-select:none}
summary::-webkit-details-marker{display:none}
summary::before{content:"\\25B8";color:var(--dim);font-size:12px;width:12px;flex:none;display:inline-block}
details[open]>summary::before{content:"\\25BE"}
details.asset:not([open])>summary.top{margin-bottom:0}
details.asset:not([open]){padding-top:12px;padding-bottom:12px}
.tools{float:right;font-size:12px;letter-spacing:0;text-transform:none;color:var(--dim)}
.tools a{color:var(--acc);cursor:pointer;margin-left:14px}
.name{font-size:17px;font-weight:600}
.badge{font-size:12px;font-weight:700;letter-spacing:.4px;padding:3px 10px;border-radius:20px}
.badge.ok{background:rgba(95,194,126,.15);color:var(--ok)}
.badge.no{background:rgba(255,107,94,.15);color:var(--err)}
.counts{color:var(--dim);font-size:12px}
.prob{margin:14px 0 4px}
.prob h3{font-size:12px;letter-spacing:.8px;margin:0 0 6px;text-transform:uppercase}
.prob.e h3{color:var(--err)} .prob.w h3{color:var(--warn)}
.prob ul{margin:0;padding-left:18px}
.prob li{margin:3px 0}
.prob .code{color:var(--dim);font:11px ui-monospace,Consolas,monospace;margin-left:8px}
.prob.e li>b:last-of-type{color:var(--err)} .prob.w li>b:last-of-type{color:var(--warn)}
.meas{color:var(--dim);font:11px ui-monospace,Consolas,monospace;margin:1px 0 0}
/* Занавес на время починки. Blender на тяжёлом ассете думает секунды, и без
   него страница выглядит так, будто кнопку не нажали: ничего не меняется, а
   строка состояния мелкая и внизу. */
.veil{position:fixed;inset:0;z-index:50;display:none;align-items:center;
      justify-content:center;background:rgba(14,15,18,.72);
      backdrop-filter:blur(2px);cursor:progress}
.veil.on{display:flex}
.veilbox{display:flex;flex-direction:column;align-items:center;gap:14px;
         padding:26px 34px;text-align:center}
.spin{width:44px;height:44px;border-radius:50%;border:3px solid rgba(122,162,247,.22);
      border-top-color:var(--acc);animation:sqcspin .8s linear infinite}
@keyframes sqcspin{to{transform:rotate(360deg)}}
.veiltext{font-size:15px;font-weight:600}
.veilhint{font-size:12px;color:var(--dim)}
body.live .pick{cursor:pointer;border-bottom:1px dashed #54555d}
body.live .pick:hover{color:var(--acc);border-bottom-color:var(--acc)}
.who .pick{margin-left:2px} .who .pick:first-child{margin-left:0}
.rough{color:var(--warn);font-weight:400}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--dim);margin:-8px 0 18px}
.legend b{font-weight:600}
body.only-bad tr.fine{display:none}
table.facts{border-collapse:collapse;width:100%;margin-top:12px}
table.facts td{padding:3px 10px 3px 0;vertical-align:top}
td.k{color:var(--dim);width:210px;white-space:nowrap}
td.v{font:13px ui-monospace,Consolas,monospace;word-break:break-word}
td.v.ok{color:var(--ok)} td.v.warn{color:var(--warn)} td.v.bad{color:var(--err)}
td.v .m{margin-right:6px;font-family:"Segoe UI",sans-serif}
td.a{width:1%;white-space:nowrap;padding-left:14px}
button.act.row{margin:0;padding:2px 10px;font-weight:600}
.norule{color:#63646c;font:11px "Segoe UI",sans-serif;margin-left:10px}
.part{border-top:1px solid var(--line);margin-top:16px;padding-top:12px}
.part h2{font-size:12px;letter-spacing:1px;color:var(--acc);margin:0;text-transform:uppercase}
.why{color:var(--dim);font:12px "Segoe UI",sans-serif;margin-left:12px}
.foot{color:var(--dim);font-size:12px;margin-top:10px}
@media print{canvas.fx{display:none}body{background:#fff;color:#000}.asset{background:#fff;border-color:#ccc}}
"""


def _e(value):
    return html.escape("" if value is None else str(value))


def _ru(n, one, few, many):
    n10, n100 = n % 10, n % 100
    word = (
        one if (n10 == 1 and n100 != 11)
        else few if (2 <= n10 <= 4 and not 12 <= n100 <= 14)
        else many
    )
    return "%d %s" % (n, word)


# ---------------------------------------------------------------- документ


def build(settings, version, project, stage, scope_label, targets, muted_keys=(), note=None):
    """Данные отчёта: то же, что показывает панель, но адресуемое по проверке."""
    findings = []
    for result in settings.results:
        if (result.object_name, result.check_id) in muted_keys:
            continue
        # None - замера не было (проверка упала). Тогда русский текст не
        # собирается: показываем машинное сообщение как есть
        try:
            values = json.loads(result.values_json) if result.values_json else None
        except ValueError:
            values = None
        findings.append({
            "object": result.object_name,
            "code": result.check_id,
            "label": result.check_label,
            "severity": SEVERITY_ERROR if result.severity == 'FAIL' else SEVERITY_WARNING,
            "message": result.message,
            "text": explain.text(result.check_id, values, result.message),
            "values": values or {},
            "can_fix": bool(result.can_fix),
            "destructive": bool(result.fix_is_destructive),
            "muted": bool(result.muted),
        })

    # разбор по объекту: что измеряли и какая норма. Собирается здесь, рядом с
    # находками, потому что состояние строки берётся из них
    rows = {}
    for obj in targets:
        rows[obj.name] = [list(row) + [None] * (6 - len(row))
                          for row in facts_mod.rows(obj, settings)]

    names = [obj.name for obj in targets]
    # Сколько проверок отработало в этот раз: включённые на этапе, по каждому
    # объекту. uv_padding не считаем - это интерактивный показ отступов, а не
    # проверка, и в списке проверок он тоже спрятан
    from . import checks as checks_mod          # лениво: здесь нет цикла импорта
    ran_ids = [c.check_id for c in settings.checks
               if c.enabled and c.check_id not in checks_mod.CHECKLIST_HIDDEN_IDS]
    ran = len(ran_ids) * len(names)
    # «чисто» считаем по парам объект-проверка: одна проверка может дать по
    # находке на каждый UV-канал, но непройденной она остаётся одной
    dirty = {(f["object"], f["code"]) for f in findings if not f["muted"]}
    bad = {f["object"] for f in findings
           if f["severity"] == SEVERITY_ERROR and not f["muted"]}
    with_issues = {f["object"] for f in findings if not f["muted"]}
    return {
        "tool": "scene_qc_validator",
        "version": version,
        "time": datetime.datetime.now().replace(microsecond=0).isoformat(" "),
        "project": project,
        "stage": stage,
        "scope": scope_label,
        "objects": names,
        "clean": [n for n in names if n not in with_issues],
        "accepted": sum(1 for n in names if n not in bad),
        "rejected": sum(1 for n in names if n in bad),
        "muted": sum(1 for r in settings.results
                     if (r.object_name, r.check_id) in muted_keys or r.muted),
        "checks_ran": ran,
        "checks_passed": max(0, ran - len(dirty)),
        "errors": sum(1 for f in findings if f["severity"] == SEVERITY_ERROR and not f["muted"]),
        "warnings": sum(1 for f in findings if f["severity"] == SEVERITY_WARNING and not f["muted"]),
        "findings": findings,
        "facts": rows,
        "note": note,
    }


def _grouped(findings):
    """Одинаковая находка на многих объектах - одна строка, а не десять.

    Находки считаются одинаковыми, когда совпадают проверка и текст с точностью
    до имени самого объекта.
    """
    out = {}
    for item in findings:
        # имя вырезаем, только если проверка сама его в текст положила
        # (`values["name"]`): иначе объект с именем «1» испортит «1 грань…»
        named = item["object"] and (item["values"] or {}).get("name") == item["object"]
        generic = item["text"].replace(item["object"], "<объект>") if named else item["text"]
        key = (item["code"], generic)
        group = out.setdefault(key, {
            "code": item["code"], "label": item["label"], "text": item["text"],
            "generic": generic, "can_fix": item["can_fix"], "values": item["values"],
            "message": item["message"], "names": [],
        })
        group["names"].append(item["object"])
    groups = list(out.values())
    for group in groups:
        if len(group["names"]) > 1:
            group["text"] = group["generic"]
    return groups


# ---------------------------------------------------------------- страница


def _pick(text, object_name, code, live, tag="b"):
    """Кликабельное имя объекта: нажатие выделяет его в Blender, как строка в панели.

    Кликает именно имя, а не вся строка находки: рядом стоит кнопка «Исправить»,
    и строка-целиком перехватывала бы нажатие по ней.
    """
    if not live:
        return "<%s>%s</%s>" % (tag, _e(text), tag)
    return ("<%s class='pick' data-obj='%s' data-code='%s' title='Показать в Blender'>"
            "%s</%s>" % (tag, _e(object_name), _e(code), _e(text), tag))


def _fix_line(code, values, can_fix):
    kind, how = explain.fix_hint(code, values, can_fix)
    if not how:
        return ""
    return "<div class='fix %s'><b>%s:</b> %s</div>" % (kind, explain.FIX_LABEL[kind], _e(how))


def _problems(doc, severity, css, title, live=None):
    """Все находки одним списком. Одинаковая находка на многих объектах - одна строка."""
    items = [f for f in doc["findings"] if f["severity"] == severity and not f["muted"]]
    if not items:
        return ""
    rows = []
    for group in _grouped(items):
        names = group["names"]
        label = explain.label(group["code"], group["label"])
        button = ""
        if live and group["can_fix"]:
            # объекты строки едут в кнопку: одна проверка даёт по строке на
            # каждый разный замер, и кнопка должна чинить свою строку
            button = ("<button class='act one' data-act='fix_code' data-code='%s' "
                      "data-obj='%s' disabled>Исправить</button>"
                      % (_e(group["code"]), _e(",".join(names))))
        who = ""
        if len(names) > 1:
            head = "<b>%s</b>" % _e(_ru(len(names), "объект", "объекта", "объектов"))
            who = "<div class='who'>%s</div>" % ", ".join(
                _pick(n, n, group["code"], live, tag="span") for n in names)
        else:
            head = _pick(names[0], names[0], group["code"], live)
        rows.append("<li>%s · <b>%s</b>: %s<span class='code'>%s</span>%s%s%s</li>"
                    % (head, _e(label), _e(group["text"]), _e(group["code"]), button, who,
                       _fix_line(group["code"], group["values"], group["can_fix"])))
    return ("<div class='prob %s'><h3>%s · %d</h3><ul>%s</ul></div>"
            % (css, _e(title), len(items), "".join(rows)))


def _how(doc, live=None):
    """Строка над списком: сколько уйдёт кнопкой, сколько руками - и сами кнопки."""
    findings = [f for f in doc["findings"] if not f["muted"]]
    if not findings:
        return ""
    kinds = [explain.fix_hint(f["code"], f["values"], f["can_fix"])[0] for f in findings]
    auto = kinds.count(explain.AUTO)
    # правка геометрии - не то же, что чистка данных: о ней надо предупредить
    rough = sum(1 for f, kind in zip(findings, kinds)
                if kind == explain.AUTO and f["destructive"])
    rough_note = (" <span class='rough'>(меняют геометрию: %d)</span>" % rough) if rough else ""
    out = ["<div class='how'>"]
    if live:
        out.append("<span class='grp'><span class='fix auto'><b>авто:</b> %d%s</span>%s</span>"
                   % (auto, rough_note,
                      "<button class='act' data-act='fix_all' disabled>Исправить "
                      "автоматически</button>" if auto else ""))
    else:
        # связи нет: отчёт переслали или Blender закрыт - сказать, чем чинить
        out.append("<span class='fix auto'><b>авто:</b> %d%s%s</span>"
                   % (auto, rough_note, (" — " + explain.AUTO_TEXT) if auto else ""))
    if kinds.count(explain.BUTTON):
        out.append("<span class='fix button'><b>кнопкой:</b> %d</span>" % kinds.count(explain.BUTTON))
    out.append("<span class='fix manual'><b>руками:</b> %d</span>" % kinds.count(explain.MANUAL))
    if kinds.count(explain.NOTE):
        out.append("<span class='fix note'><b>к сведению:</b> %d</span>" % kinds.count(explain.NOTE))
    if doc.get("muted"):
        out.append("<span class='fix note' title='Правила, выключенные для этих объектов "
                   "вручную: в счёт ошибок они не идут'><b>заглушено:</b> %d</span>"
                   % doc["muted"])
    if live:
        out.append("<span id='live' class='live'>Связь с Blender…</span>")
    out.append("</div>")
    return "".join(out)


def _note(doc):
    """Итог действия, запущенного кнопкой: что сделано и что осталось за человеком."""
    action = doc.get("note")
    if not action:
        return ""
    return "<div class='note%s'>%s</div>" % ("" if action.get("ok") else " bad",
                                             _e(action.get("text", "")))


def _is_clean(doc):
    """Повод для салюта: ни ошибок, ни замечаний, и ничего не отклонено."""
    return bool(doc["objects"]) and not (doc["errors"] or doc["warnings"]
                                         or doc["rejected"])


def _tiles(doc):
    return ("<div class='tiles'>"
            "<div class='tile ok'><b>%d</b><span>принято</span></div>"
            "<div class='tile %s'><b>%d</b><span>отклонено</span></div>"
            "<div class='tile %s'><b>%d</b><span>ошибок</span></div>"
            "<div class='tile %s'><b>%d</b><span>замечаний</span></div>"
            "<div class='tile'><b>%d</b><span>объектов</span></div>"
            # отдельно, с отступом: это не про находки, а про объём работы
            "<div class='tile apart'><b>%d из %d</b>"
            "<span>проверок без замечаний</span></div></div>"
            % (doc["accepted"], "no" if doc["rejected"] else "", doc["rejected"],
               "no" if doc["errors"] else "", doc["errors"],
               "w" if doc["warnings"] else "", doc["warnings"], len(doc["objects"]),
               doc.get("checks_passed", 0), doc.get("checks_ran", 0)))


# подписи строк разбора, которые идут отдельными колонками сводки
_SUMMARY_COLUMNS = (("Тр.", "Треугольников"), ("UV", "UV-каналов"),
                    ("Материалы", "Материалы"), ("Пивот", "Пивот"),
                    ("Трансформ.", "Трансформация"))


def _cell(value, state):
    css = "dim" if state in (None, facts_mod.INFO) else state
    return "<td class='%s'>%s</td>" % (css, _e(value))


def _table(doc):
    """По строке на объект: вердикт, главные признаки и счёт - расхождения видны
    глазами, без чтения карточек."""
    rows = []
    for name in doc["objects"]:
        own = [f for f in doc["findings"] if f["object"] == name and not f["muted"]]
        errors = sum(1 for f in own if f["severity"] == SEVERITY_ERROR)
        warnings = len(own) - errors
        by_label = {row[0]: row for row in doc.get("facts", {}).get(name) or []}
        cells = "".join(
            _cell(by_label[label][4] or by_label[label][1], by_label[label][2])
            if label in by_label else _cell("—", None)
            for _head, label in _SUMMARY_COLUMNS)
        rows.append(
            "<tr class='%s'><td>%s</td><td class='%s'>%s</td>%s"
            "<td class='n %s'>%d</td><td class='n %s'>%d</td></tr>"
            % ("" if own else "clean", _e(name),
               "bad" if errors else "ok", VERDICT_BAD if errors else VERDICT_OK, cells,
               "bad" if errors else "dim", errors,
               "warn" if warnings else "dim", warnings)
        )
    if not rows:
        return ""
    head = "".join("<th>%s</th>" % _e(h) for h, _label in _SUMMARY_COLUMNS)
    return ("<div class='card scroll'><table class='sum'><tr><th>Объект</th><th>Вердикт</th>"
            "%s<th>Ошибок</th><th>Замеч.</th></tr>%s</table></div>" % (head, "".join(rows)))


def _problem_list(doc, name, severity, css, title, live=None):
    """Находки одного объекта внутри его карточки."""
    rows = []
    for finding in doc["findings"]:
        if finding["object"] != name or finding["severity"] != severity or finding["muted"]:
            continue
        label = explain.label(finding["code"], finding["label"])
        # машинный замер - под русским текстом, но только если он другой:
        # у проверки без сборщика текста это одна и та же строка
        meas = ("<div class='meas'>%s</div>" % _e(finding["message"])
                if finding["message"] and finding["message"] != finding["text"] else "")
        rows.append("<li><b>%s</b>: %s<span class='code'>%s</span>%s%s</li>"
                    % (_e(label), _e(finding["text"]), _e(finding["code"]), meas,
                       _fix_line(finding["code"], finding["values"], finding["can_fix"])))
    if not rows:
        return ""
    return "<div class='prob %s'><h3>%s</h3><ul>%s</ul></div>" % (css, _e(title), "".join(rows))


_MARK = {facts_mod.OK: "✓", facts_mod.BAD: "✕", facts_mod.WARN: "!"}
NO_RULE = "<span class='norule'>правила нет</span>"


def _facts_table(doc, name, live=None):
    """Разбор объекта: значение, состояние, норма. Что измеряли - видно и тогда,
    когда находок нет."""
    rows = doc.get("facts", {}).get(name) or []
    out = []
    for label, value, state, why, _short, action in rows:
        # серое без пояснения читается как «забыли проверить»; говорим прямо
        tail = NO_RULE if state is None else ""
        if state in (facts_mod.WARN, facts_mod.BAD) and why:
            tail = "<span class='why'>%s</span>" % _e(why)
        mark = ("<span class='m'>%s</span>" % _MARK[state]) if state in _MARK else ""
        css = "" if state is facts_mod.INFO else (state or "")
        # кнопка у строки: показать то, о чём строка, прямо в Blender
        button = ""
        if live and action:
            button = ("<button class='act row' data-act='%s' data-obj='%s' disabled>%s"
                      "</button>" % (_e(action[1]), _e(name), _e(action[0])))
        out.append("<tr%s><td class='k'>%s</td><td class='v %s'>%s%s%s</td>"
                   "<td class='a'>%s</td></tr>"
                   % ("" if state in (facts_mod.WARN, facts_mod.BAD) else " class='fine'",
                      _e(label), css, mark, _e(value), tail, button))
    if not out:
        return ""
    return ("<div class='part'><h2>Разбор</h2><table class='facts'>%s</table></div>"
            % "".join(out))


def _cards(doc, live=None):
    """Карточка на объект. По умолчанию раскрыты только те, где есть ошибки."""
    out = []
    for name in doc["objects"]:
        own = [f for f in doc["findings"] if f["object"] == name and not f["muted"]]
        errors = sum(1 for f in own if f["severity"] == SEVERITY_ERROR)
        warnings = len(own) - errors
        counts = " · ".join(x for x in (
            _ru(errors, "ошибка", "ошибки", "ошибок") if errors else "",
            _ru(warnings, "замечание", "замечания", "замечаний") if warnings else "",
        ) if x) or "без замечаний"
        out.append(
            "<details class='asset%s'%s data-k='a:%s'><summary class='top'>"
            "<span class='name'>%s</span><span class='badge %s'>%s</span>"
            "<span class='counts'>%s</span></summary>%s%s</details>"
            % ("" if own else " clean", " open" if errors else "", _e(name), _e(name),
               "no" if errors else "ok", VERDICT_BAD if errors else VERDICT_OK, _e(counts),
               _problem_list(doc, name, SEVERITY_ERROR, "e", "Ошибки", live)
               + _problem_list(doc, name, SEVERITY_WARNING, "w", "Замечания", live),
               _facts_table(doc, name, live))
        )
    return "".join(out)


# Скрипт страницы, записанной Blender со связью (см. live.py). Раз в полторы
# секунды спрашивает номер текущего отчёта; изменился - забирает новую страницу и
# подменяет содержимое на месте, сохраняя прокрутку и раскрытые карточки. Нажатие
# кнопки уходит в Blender командой из его списка. Нет связи - кнопки выключены.
JS_VIEW = """
function syncAll(){var c=document.getElementById('showall');if(c)c.checked=!document.body.classList.contains('only-bad');}
document.addEventListener('change',function(e){
  if(e.target&&e.target.id==='showall')document.body.classList.toggle('only-bad',!e.target.checked);
});
"""

# Салют: плитка «принято» трясётся всё сильнее и раскаляется, взрывается искрами, следом два залпа
# конфетти из нижних углов окна. Играет один раз на свежем отчёте, где всё принято и нет ни одного
# замечания (data-party ставит редактор, см. party()). Отчёт, открытый позже или пересланный, не салютует: страница
# сверяет своё время с часами.
# Рисуется на двух холстах поверх страницы, мышь они не перехватывают: на одном искры (старый
# кадр гаснет - остаётся след), на другом конфетти (кадр стирается целиком).
JS_PARTY = """
(function(){
var cvA=null,cvB=null,ctxA,ctxB,ctx,W=0,H=0,U=1,items=[],queue=[],raf=null,last=0,t=0,done={};
var GOLD=[42,45,66],GREEN=[139,45,57],WHITE=[40,20,94];
var PAPER=['#C9B489','#5fc27e','#7aa2f7','#ff6b5e','#e6e6e8','#e8b23a'];
function R(a,b){return a+Math.random()*(b-a);}
function hsla(c,a){return 'hsla('+c[0]+','+c[1]+'%,'+c[2]+'%,'+a+')';}
function size(){
  var d=Math.min(window.devicePixelRatio||1,2);
  W=window.innerWidth;H=window.innerHeight;U=Math.min(W,H)/900;
  cvA.width=cvB.width=W*d;cvA.height=cvB.height=H*d;
  ctxA.setTransform(d,0,0,d,0,0);ctxB.setTransform(d,0,0,d,0,0);
}
function setup(){
  if(cvA)return;
  cvA=document.createElement('canvas');cvB=document.createElement('canvas');
  cvA.className=cvB.className='fx';
  document.body.appendChild(cvA);document.body.appendChild(cvB);
  ctxA=cvA.getContext('2d');ctxB=cvB.getContext('2d');ctx=ctxA;
  window.addEventListener('resize',size);size();
}
function at(ms,fn){queue.push({at:ms,fn:fn});queue.sort(function(a,b){return a.at-b.at;});}
function spark(x,y,vx,vy,o){
  return {x:x,y:y,px:x,py:y,vx:vx,vy:vy,life:o.life,max:o.life,c:o.c,w:o.w,g:o.g,d:o.d,
    step:function(k){
      this.px=this.x;this.py=this.y;
      var dd=Math.pow(this.d,k);
      this.vx*=dd;this.vy=this.vy*dd+this.g*U*k;
      this.x+=this.vx*k;this.y+=this.vy*k;this.life-=k;
      return this.life>0;
    },
    draw:function(){
      ctx.strokeStyle=hsla(this.c,Math.min(1,this.life/this.max*1.7));ctx.lineWidth=this.w;ctx.lineCap='round';
      ctx.beginPath();ctx.moveTo(this.px,this.py);ctx.lineTo(this.x,this.y);ctx.stroke();
    }};
}
function flash(x,y,r,c,life){
  return {life:life,step:function(k){this.life-=k;return this.life>0;},
    draw:function(){
      var a=this.life/life,g=ctx.createRadialGradient(x,y,0,x,y,r);
      g.addColorStop(0,hsla(c,0.55*a));g.addColorStop(1,hsla(c,0));
      ctx.fillStyle=g;ctx.beginPath();ctx.arc(x,y,r,0,6.2832);ctx.fill();
    }};
}
function burst(x,y,n,speed,o){
  if(!o.dark)items.push(flash(x,y,speed*14,o.c,10));
  for(var i=0;i<n;i++){
    var a=Math.random()*6.2832,v=speed*(Math.random()<0.7?R(0.85,1):R(0.25,0.8));
    items.push(spark(x,y,Math.cos(a)*v,Math.sin(a)*v,
      {life:R(o.life*0.75,o.life*1.15),c:Math.random()<o.mix?WHITE:o.c,w:o.w,g:o.g,d:o.d}));
  }
}
function ring(x,y,c,r1){
  var p=0;
  return {step:function(k){p+=k/22;return p<1;},
    draw:function(){
      var e=1-(1-p)*(1-p);
      ctx.strokeStyle=hsla(c,0.7*(1-p));ctx.lineWidth=5*(1-p)+1;
      ctx.beginPath();ctx.arc(x,y,r1*e,0,6.2832);ctx.stroke();
    }};
}
function piece(x,y,vx,vy){
  var w=R(6,10),h=R(9,15),rot=R(0,6.28),vr=R(-0.25,0.25),ph=R(0,6.28),vph=R(0.12,0.3);
  var col=PAPER[Math.floor(Math.random()*PAPER.length)];
  return {flat:true,step:function(k){
      var d=Math.pow(0.985,k);vx*=d;vy=vy*d+0.22*U*k;
      x+=(vx+Math.sin(ph)*0.9)*k;y+=vy*k;rot+=vr*k;ph+=vph*k;
      return y<H+40;
    },
    draw:function(){
      ctx.save();ctx.translate(x,y);ctx.rotate(rot);ctx.scale(1,Math.cos(ph));
      ctx.fillStyle=col;ctx.fillRect(-w/2,-h/2,w,h);ctx.restore();
    }};
}
function cannon(side,n){
  for(var i=0;i<n;i++){
    var a=(side<0?R(-78,-38):R(-142,-102))*Math.PI/180,v=R(13,27)*U;
    items.push(piece(side<0?-10:W+10,H+10,Math.cos(a)*v,Math.sin(a)*v));
  }
}
function wipe(){ctxA.globalCompositeOperation='source-over';ctxA.clearRect(0,0,W,H);ctxB.clearRect(0,0,W,H);}
function tick(dt){
  var k=dt/16.667;t+=dt;
  while(queue.length&&queue[0].at<=t)queue.shift().fn();
  ctxA.globalCompositeOperation='destination-out';
  ctxA.fillStyle='rgba(0,0,0,'+(1-Math.pow(0.78,k))+')';ctxA.fillRect(0,0,W,H);
  ctxA.globalCompositeOperation='lighter';
  ctxB.clearRect(0,0,W,H);
  var alive=[];
  for(var i=0;i<items.length;i++)if(items[i].step(k))alive.push(items[i]);
  items=alive;
  for(var j=0;j<items.length;j++){ctx=items[j].flat?ctxB:ctxA;items[j].draw();}
}
function frame(now){
  var dt=Math.min(now-last,50);last=now;tick(dt);
  if(items.length||queue.length){raf=requestAnimationFrame(frame);}else{wipe();raf=null;}
}
function party(seek){
  var page=document.getElementById('root'),tile=page&&page.querySelector('.tile.ok');
  if(!tile)return;
  setup();
  if(raf)cancelAnimationFrame(raf);
  items=[];queue=[];t=0;last=performance.now();wipe();
  var r=tile.getBoundingClientRect();
  if(r.bottom<0||r.top>H){window.scrollTo(0,0);r=tile.getBoundingClientRect();}
  var x=r.left+r.width/2,y=r.top+r.height/2,T=1500,ph=0;
  tile.style.position='relative';tile.style.zIndex='5';tile.style.transition='none';
  function boom(){
    tile.style.transform='scale(1.45)';tile.style.filter='brightness(2.4)';
    at(t+40,function(){
      tile.style.transition='transform .5s cubic-bezier(.2,1.7,.4,1),filter .5s,box-shadow .7s';
      tile.style.transform='';tile.style.filter='';tile.style.boxShadow='';
      void tile.offsetWidth;tile.classList.add('pulse');
    });
    at(t+900,function(){tile.style.cssText='';});
    items.push(flash(x,y,190*U,WHITE,9));
    items.push(ring(x,y,GREEN,240*U));
    burst(x,y,46,15*U,{c:WHITE,life:26,mix:1,g:0.06,d:0.94,w:2.2,dark:1});
    burst(x,y,120,10.5*U,{c:GREEN,life:62,mix:0.2,g:0.11,d:0.965,w:2});
    at(t+90,function(){burst(x,y,70,6.5*U,{c:GOLD,life:52,mix:0,g:0.11,d:0.965,w:1.6});});
    var q=0;
    items.push({step:function(k){
        q+=k/18;
        if(q>=1){page.style.transform='';return false;}
        var a=(1-q)*(1-q)*8;
        page.style.transform='translate('+R(-a,a).toFixed(1)+'px,'+R(-a,a).toFixed(1)+'px)';
        return true;
      },draw:function(){}});
    at(t+300,function(){cannon(-1,130);cannon(1,130);});
    at(t+850,function(){cannon(-1,110);cannon(1,110);});
  }
  items.push({step:function(k){
      var p=Math.min(t/T,1),a=p*p;
      ph+=k*(0.7+p*2.6);
      var dx=Math.sin(ph*1.9)*a*8+R(-1,1)*a*4,dy=Math.cos(ph*2.3)*a*5+R(-1,1)*a*3,
          rot=Math.sin(ph*1.3)*a*4+R(-1,1)*a*1.5,sc=1+0.2*p*p*p;
      tile.style.transform='translate('+dx.toFixed(1)+'px,'+dy.toFixed(1)+'px) rotate('+rot.toFixed(2)+'deg) scale('+sc.toFixed(3)+')';
      tile.style.boxShadow='0 0 '+(6+50*a).toFixed(0)+'px '+(1+12*a).toFixed(0)+'px rgba(95,194,126,'+(0.12+0.8*a).toFixed(2)+')';
      tile.style.borderColor='#5fc27e';tile.style.filter='brightness('+(1+0.9*a).toFixed(2)+')';
      if(Math.random()<a*0.8*k){
        var ang=Math.random()*6.2832,v=R(2,5.5)*U;
        items.push(spark(x+Math.cos(ang)*r.width*0.5,y+Math.sin(ang)*r.height*0.5,Math.cos(ang)*v,Math.sin(ang)*v,
          {life:R(14,26),c:Math.random()<0.4?WHITE:GREEN,w:1.5,g:0.09,d:0.96}));
      }
      if(p>=1){boom();return false;}
      return true;
    },draw:function(){}});
  // seek - показать эффект на заданной миллисекунде, без анимации: для снимков при проверке
  if(seek){while(t<seek)tick(16.667);}else{raf=requestAnimationFrame(frame);}
}
function check(){
  var root=document.getElementById('root');
  if(!root||root.getAttribute('data-party')!=='1')return;
  var key=root.getAttribute('data-time')||'';
  if(done[key])return;
  if(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  var age=Date.now()-new Date(key).getTime();
  if(!(age>-5000&&age<90000))return;
  done[key]=1;
  if(document.visibilityState==='visible'&&document.hasFocus()){party();return;}
  var vis=function(){if(document.visibilityState==='visible'&&document.hasFocus())go();};
  var go=function(){
    window.removeEventListener('focus',go);document.removeEventListener('visibilitychange',vis);
    var r=document.getElementById('root');
    if(r&&r.getAttribute('data-time')===key&&r.getAttribute('data-party')==='1')party();
  };
  window.addEventListener('focus',go);document.addEventListener('visibilitychange',vis);
}
window.metParty=party;window.metPartyCheck=check;
check();
})();
"""

JS_LIVE = """
(function(){
var L=__LIVE__,root=document.getElementById('root'),rev=root.getAttribute('data-rev');
var pending=null,fails=0,state=null,msg=null,dead=false;
function url(p,q){return 'http://127.0.0.1:'+L.port+p+'?t='+encodeURIComponent(L.token)+(q||'');}
function call(u,opt){
  var c=new AbortController(),t=setTimeout(function(){c.abort();},4000);
  opt=opt||{};opt.signal=c.signal;opt.cache='no-store';
  return fetch(u,opt).then(function(r){clearTimeout(t);return r;},function(e){clearTimeout(t);throw e;});
}
function status(cls,text){var s=document.getElementById('live');if(s){s.className='live '+cls;s.textContent=text;}}
function enable(on){var b=document.querySelectorAll('button.act');for(var i=0;i<b.length;i++)b[i].disabled=!on;}
function show(){
  if(dead){enable(false);status('off','Отчёт от прошлого запуска Blender — запустите проверку заново');return;}
  if(pending){enable(false);status('run','Blender выполняет: '+pending.label+'…');return;}
  if(!state){enable(false);status('off',fails>1?'Нет связи с Blender — кнопки работают, пока открыт Blender, из которого сделана проверка':'Связь с Blender…');return;}
  if(state.busy){enable(false);status('run','Blender занят…');return;}
  enable(true);
  if(msg){status(msg.ok?'on':'off',msg.text);}else{status('on','Blender на связи');}
}
function opened(){var m={},d=root.querySelectorAll('details[data-k]');for(var i=0;i<d.length;i++)m[d[i].getAttribute('data-k')]=d[i].open;return m;}
function swap(){
  return call(url('/report')).then(function(r){if(!r.ok)throw 0;return r.text();}).then(function(t){
    var n=new DOMParser().parseFromString(t,'text/html').getElementById('root');
    if(!n)return;
    var m=opened();
    root.innerHTML=n.innerHTML;rev=n.getAttribute('data-rev');msg=null;syncAll();
    // время и признак салюта - у корня страницы: переносим их с новой версии
    // и спрашиваем, не пора ли
    root.setAttribute('data-time',n.getAttribute('data-time')||'');
    if(n.getAttribute('data-party'))root.setAttribute('data-party','1');
    else root.removeAttribute('data-party');
    if(window.metPartyCheck)window.metPartyCheck();
    var d=root.querySelectorAll('details[data-k]');
    for(var i=0;i<d.length;i++){var k=d[i].getAttribute('data-k');if(k in m)d[i].open=m[k];}
  });
}
function poll(){
  call(url('/state','&v='+(document.visibilityState==='visible'?1:0)))
  .then(function(r){
    // 403 - на этом порту уже другой Blender: токен страницы ему чужой
    if(r.status===403){dead=true;return null;}
    if(!r.ok)throw 0;return r.json();
  }).then(function(s){
    if(dead||!s){show();return;}
    fails=0;state=s;
    if(pending){
      if(s.last&&s.last.id===pending.id){pending=null;if(String(s.rev)===String(rev))msg=s.last;}
      else if(pending.unsure&&!s.busy){pending=null;msg={ok:false,text:'Команда не дошла до Blender — нажмите ещё раз'};}
    }
    if(s.rev&&String(s.rev)!==String(rev))return swap().then(show,show);
    show();
  }).catch(function(){
    fails++;if(fails>1)state=null;
    if(pending&&(fails>200||(pending.unsure&&fails>2))){pending=null;msg=null;}
    show();
  }).then(function(){
    // мёртвая страница замолкает: пересланный отчёт не должен вечно стучаться
    // в 127.0.0.1 на чужой машине. Молчащий Blender опрашиваем всё реже.
    if(dead)return;
    setTimeout(poll,fails>20?15000:fails>3?5000:1500);
  });
}
document.body.classList.add('live');
var veilEl=document.getElementById('veil'),veilTx=document.getElementById('veiltext'),veilOff=false;
function veil(text){
  if(!veilEl)return;
  if(text&&!veilOff){veilTx.textContent=text;veilEl.classList.add('on');}
  else veilEl.classList.remove('on');
}
// занавес снимается кликом: если Blender молчит, человек не должен остаться
// заперт за тёмным экраном
if(veilEl)veilEl.addEventListener('click',function(){veilOff=true;veil('');});
// занавес ходит за pending сам: тот гасится в пяти разных местах, и развешивать
// вызовы по каждому - верный способ однажды оставить экран тёмным
setInterval(function(){veil(pending&&pending.heavy?pending.label:'');},120);
function send(label,q,heavy){
  var id=String(Date.now())+Math.random().toString(36).slice(2,8);
  pending={id:id,label:label,heavy:!!heavy};msg=null;veilOff=false;
  veil(heavy?label:'');show();
  // страховка: пять минут ожидания - это уже не ожидание
  setTimeout(function(){if(pending&&pending.id===id){veilOff=true;veil('');}},300000);
  call(url('/run','&id='+id+q),{method:'POST'}).then(function(r){
    if(r.status===409){pending=null;msg={ok:false,text:'Blender занят — повторите чуть позже'};show();}
    else if(!r.ok){pending=null;msg={ok:false,text:'Blender не принял команду'};show();}
  },function(){if(pending&&pending.id===id)pending.unsure=true;});
}
document.addEventListener('click',function(e){
  if(!e.target.closest)return;
  var b=e.target.closest('button.act');
  if(b){
    if(b.disabled||pending)return;
    var act=b.getAttribute('data-act')||'';
    // занавес только для починки: «показать в Blender» отрабатывает мгновенно,
    // и темнеть ради него - мешать
    send(b.textContent.trim(),'&a='+encodeURIComponent(act)
         +'&code='+encodeURIComponent(b.getAttribute('data-code')||'')
         +'&obj='+encodeURIComponent(b.getAttribute('data-obj')||''),
         act.indexOf('fix')===0);
    return;
  }
  var row=e.target.closest('.pick');
  if(!row||pending)return;
  send('показать в Blender','&a=select&code='+encodeURIComponent(row.getAttribute('data-code'))
       +'&obj='+encodeURIComponent(row.getAttribute('data-obj')));
});
show();poll();
})();
"""


def render(doc, live=None):
    """live - {"port", "token", "rev"} от live.py: страница получает кнопки и
    обновляется сама. Без него это прежняя самодостаточная страница."""
    out = ["<!doctype html><html lang='ru'><meta charset='utf-8'>",
           "<title>Mutaform: Scene Quality Control</title>",
           "<style>%s</style><body>" % CSS,
           "<div id='root'%s data-time='%s'%s>" % (
               (" data-rev='%s'" % _e(live["rev"])) if live else "", _e(doc["time"]),
               " data-party='1'" if _is_clean(doc) else ""),
           "<div class='head'>%s<div class='div'></div>"
           "<h1>Scene <span>Quality Control</span></h1>"
           "<label class='all' title='Выключите, чтобы остались только объекты с находками "
           "и строки не по правилам'>"
           "<input type='checkbox' id='showall' checked>Показывать всё</label></div>" % LOGO,
           "<div class='sub'>%s · проект <b>%s</b> · этап <b>%s</b> · область <b>%s</b> · "
           "проверено %d · принято %d, отклонено %d</div>"
           % (_e(doc["time"]), _e(doc["project"]), _e(doc["stage"]), _e(doc["scope"]),
              len(doc["objects"]), doc["accepted"], doc["rejected"]),
           "<div class='legend'>"
           "<span style='color:var(--ok)'><b>✓ зелёное</b> — по правилам этапа</span>"
           "<span style='color:var(--warn)'><b>! жёлтое</b> — в допуске, но стоит взглянуть</span>"
           "<span style='color:var(--err)'><b>✕ красное</b> — против правил</span>"
           "<span>серое — справочно или правила нет</span></div>",
           _note(doc),
           _tiles(doc)]

    problems = (_problems(doc, SEVERITY_ERROR, "e", "Ошибки", live)
                + _problems(doc, SEVERITY_WARNING, "w", "Замечания", live))
    out.append("<h2 class='sec'>Что исправить</h2><div class='card'>%s%s</div>"
               % (_how(doc, live),
                  problems or
                  ("<div class='allgood'>🎉 Чисто: ассет прошёл все проверки"
                   "<span>%d из %d, ни одного замечания</span></div>"
                   % (doc.get("checks_passed", 0), doc.get("checks_ran", 0)))))

    table = _table(doc)
    if table:
        out.append("<h2 class='sec'>Объекты · сводка</h2>" + table)
    out.append("<h2 class='sec'>Подробно<span class='tools'>"
               "<a onclick=\"document.querySelectorAll('details.asset').forEach("
               "function(d){d.open=true})\">развернуть все</a>"
               "<a onclick=\"document.querySelectorAll('details.asset').forEach("
               "function(d){d.open=false})\">свернуть все</a></span></h2>")
    out.append(_cards(doc, live))

    out.append("<div class='foot'>Mutaform Scene QC Validator %s · машинная версия отчёта "
               "рядом, qc_report.json</div></div>" % _e(doc["version"]))
    if live:
        # вне #root: swap() перерисовывает только его, а занавес должен
        # пережить обновление страницы и сняться сам
        out.append(
            "<div class='veil' id='veil'><div class='veilbox'>"
            "<div class='spin'></div>"
            "<div class='veiltext' id='veiltext'></div>"
            "<div class='veilhint'>Blender работает — окно обновится само</div>"
            "</div></div>")
    out.append("<script>%s</script>" % JS_VIEW)
    out.append("<script>%s</script>" % JS_PARTY)
    if live:
        out.append("<script>%s</script>" % JS_LIVE.replace(
            "__LIVE__", json.dumps({"port": live["port"], "token": live["token"]})))
    out.append("</body></html>")
    return "".join(out)


def write(doc, directory, name="qc_report", live=None):
    """Пишем через временный файл: страницу в этот момент может читать открытая вкладка."""
    try:
        path = os.path.join(directory, name + ".html")
        text = render(doc, live)
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as page:
                page.write(text)
            os.replace(tmp, path)
        except OSError:
            with open(path, "w", encoding="utf-8") as page:
                page.write(text)
    except Exception:
        return None
    try:
        with open(os.path.join(directory, name + ".json"), "w", encoding="utf-8") as data:
            json.dump(doc, data, ensure_ascii=False, indent=1)
    except (OSError, TypeError, ValueError):
        pass
    return path


def open_in_browser(path):
    try:
        os.startfile(path)
        return True
    except (OSError, AttributeError):
        try:
            import webbrowser
            return webbrowser.open("file:///" + path.replace("\\", "/"))
        except Exception:
            return False
