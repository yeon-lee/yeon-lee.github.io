/*
 * Quantum Computing tab (_pages/quantum-computing.md).
 *
 *   1. "same distance, fewer qubits" figure   _includes/qc/budget.liquid
 *   2. qubit-estimate chart                   _includes/qc/estimates.liquid
 *   3. blueprint panels and topic sections    _includes/qc/blueprint.liquid
 *   4. milestone filters                      _includes/qc/timeline.liquid
 *
 * Data come from <script type="application/json"> blocks that the includes
 * write from _data/qc_*.yml. Plain ES5, no libraries, no build step. Without
 * JavaScript the page still reads: the captions carry the numbers, the sources
 * table lists every chart point, and all sections stay open.
 */
(function () {
  'use strict';

  var SVG_NS = 'http://www.w3.org/2000/svg';

  function svgEl(name, attrs, parent) {
    var node = document.createElementNS(SVG_NS, name);
    var key;
    if (attrs) {
      for (key in attrs) {
        if (Object.prototype.hasOwnProperty.call(attrs, key) && attrs[key] !== null && attrs[key] !== undefined) {
          node.setAttribute(key, attrs[key]);
        }
      }
    }
    if (parent) parent.appendChild(node);
    return node;
  }

  function readJSON(root, selector) {
    var node = root.querySelector(selector);
    if (!node) return null;
    try {
      return JSON.parse(node.textContent);
    } catch (err) {
      return null;
    }
  }

  function each(list, fn) {
    Array.prototype.forEach.call(list, fn);
  }

  function commas(value) {
    return String(Math.round(value)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function cssVar(name, fallback) {
    var value = window.getComputedStyle(document.documentElement).getPropertyValue(name);
    return value && value.trim() ? value.trim() : fallback;
  }

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  /* ---- 1. same distance, fewer qubits ------------------------------------ */

  function initBudget(root) {
    var codes = readJSON(root, '[data-qc-codes]');
    var plot = root.querySelector('[data-qc-plot]');
    if (!codes || !codes.length || !plot) return null;

    var lead = root.querySelector('[data-qc-lead]');
    var oursText = root.querySelector('[data-qc-ours]');
    var baseText = root.querySelector('[data-qc-base]');
    var buttons = root.querySelectorAll('[data-qc-choice]');
    var current = 0;
    var animate = false;

    function codeName(c) {
      return '[[' + c.n + ',' + c.k + ',' + c.d + ']]';
    }

    function draw() {
      var c = codes[current];
      var width = plot.clientWidth || 640;
      var narrow = width < 520;
      var n = c.n;
      var k = c.k;
      var d = c.d;
      var surface = k * d * d;
      var i;

      /* our code: one near-square block of n data qubits */
      var oCols = Math.ceil(Math.sqrt(n));
      var oRows = Math.ceil(n / oCols);

      /* surface code: k patches of d x d, wide on desktop, squarer on phones */
      var tCols = Math.max(1, Math.min(k, Math.round(Math.sqrt(k * (narrow ? 1.1 : 2.4)))));
      var tRows = Math.ceil(k / tCols);
      var gap = 1;
      var tW = tCols * d + (tCols - 1) * gap;
      var tH = tRows * d + (tRows - 1) * gap;
      var sep = Math.max(4, Math.round(Math.max(tW, tH) * 0.05));

      var W, H, sx, sy;
      if (narrow) {
        W = Math.max(oCols, tW);
        H = oRows + sep + tH;
        sx = 0;
        sy = oRows + sep;
      } else {
        W = oCols + sep + tW;
        H = Math.max(oRows, tH);
        sx = oCols + sep;
        sy = 0;
      }

      var U = 10;
      var dotted = width / W >= 2.6;
      var oursColor = cssVar('--qc-ours', '#d9473b');
      var baseColor = cssVar('--qc-base', '#87929f');

      var svg = svgEl('svg', {
        viewBox: '-4 -4 ' + (W * U + 8) + ' ' + (H * U + 8),
        'class': 'qc-budget-svg' + (animate ? ' is-entering' : ''),
        'aria-hidden': 'true',
        focusable: 'false'
      });

      var patternId = 'qc-dots-' + current;
      if (dotted) {
        var defs = svgEl('defs', null, svg);
        var pattern = svgEl('pattern', { id: patternId, width: U, height: U, patternUnits: 'userSpaceOnUse' }, defs);
        svgEl('circle', { cx: U / 2, cy: U / 2, r: U * 0.32, fill: baseColor }, pattern);
      }

      var patches = svgEl('g', null, svg);
      for (i = 0; i < k; i++) {
        var x = (sx + (i % tCols) * (d + gap)) * U;
        var y = (sy + Math.floor(i / tCols) * (d + gap)) * U;
        if (dotted) {
          svgEl('rect', { x: x, y: y, width: d * U, height: d * U, 'class': 'qc-patch-bg' }, patches);
          svgEl('rect', { x: x, y: y, width: d * U, height: d * U, fill: 'url(#' + patternId + ')' }, patches);
        } else {
          svgEl('rect', { x: x, y: y, width: d * U, height: d * U, 'class': 'qc-patch-flat' }, patches);
        }
      }
      svgEl('rect', { x: sx * U - 3, y: sy * U - 3, width: d * U + 6, height: d * U + 6, 'class': 'qc-patch-outline' }, svg);

      var block = svgEl('g', { fill: oursColor }, svg);
      if (dotted) {
        for (i = 0; i < n; i++) {
          svgEl('circle', { cx: (i % oCols) * U + U / 2, cy: Math.floor(i / oCols) * U + U / 2, r: U * 0.32 }, block);
        }
      } else {
        var fullRows = Math.floor(n / oCols);
        var rest = n - fullRows * oCols;
        svgEl('rect', { x: 0, y: 0, width: oCols * U, height: fullRows * U }, block);
        if (rest) svgEl('rect', { x: 0, y: fullRows * U, width: rest * U, height: U }, block);
      }

      plot.innerHTML = '';
      plot.appendChild(svg);

      if (lead) lead.textContent = Math.round(surface / n) + ' times fewer qubits at the same code distance';
      if (oursText) {
        oursText.innerHTML = 'Our <a href="' + c.link + '">' + codeName(c) + ' code</a>: ' + commas(n) +
          ' data qubits hold ' + k + ' logical qubits.';
      }
      if (baseText) {
        baseText.textContent = 'Surface code at the same distance ' + d + ': one ' + d + ' \u00d7 ' + d +
          ' patch per logical qubit (one is outlined), ' + commas(surface) + ' data qubits in all.';
      }
      plot.setAttribute('aria-label', 'At code distance ' + d + ', our ' + codeName(c) + ' code stores ' + k +
        ' logical qubits in ' + commas(n) + ' data qubits; surface codes need ' + commas(surface) + '.');
    }

    function choose(index) {
      current = index;
      animate = !reducedMotion();
      each(buttons, function (b) {
        b.setAttribute('aria-pressed', String(Number(b.getAttribute('data-qc-choice')) === index));
      });
      draw();
    }

    each(buttons, function (b) {
      b.addEventListener('click', function () {
        choose(Number(b.getAttribute('data-qc-choice')));
      });
    });

    draw();
    return function () {
      animate = false;
      draw();
    };
  }

  /* ---- 2. qubit-estimate chart ---------------------------------------------- */

  function initEstimates(root) {
    var data = readJSON(root, '[data-qc-estimates-data]');
    var plot = root.querySelector('[data-qc-plot]');
    if (!data || !data.points || !plot) return null;

    var LONG = ['10 thousand', '100 thousand', '1 million', '10 million', '100 million', '1 billion'];
    var SHORT = ['10k', '100k', '1M', '10M', '100M', '1B'];

    function draw() {
      var width = plot.clientWidth || 640;
      var narrow = width < 560;
      var height = narrow ? 320 : 360;
      var m = { top: 16, right: 16, bottom: 30, left: narrow ? 40 : 96 };
      var x0 = 2011.4;
      var x1 = 2027;
      var y0 = 3.2;
      var y1 = 9.4;
      var e, t, j;

      function X(v) {
        return m.left + (v - x0) / (x1 - x0) * (width - m.left - m.right);
      }
      function Y(q) {
        return m.top + (y1 - Math.log(q) / Math.LN10) / (y1 - y0) * (height - m.top - m.bottom);
      }

      var svg = svgEl('svg', {
        width: width,
        height: height,
        viewBox: '0 0 ' + width + ' ' + height,
        'class': 'qc-chart' + (narrow ? ' is-narrow' : ''),
        'aria-hidden': 'true',
        focusable: 'false'
      });

      for (e = 4; e <= 9; e++) {
        var gy = Y(Math.pow(10, e));
        svgEl('line', { x1: m.left, x2: width - m.right, y1: gy, y2: gy, 'class': 'qc-grid' }, svg);
        t = svgEl('text', { x: m.left - 8, y: gy + 4, 'text-anchor': 'end', 'class': 'qc-axis' }, svg);
        t.textContent = (narrow ? SHORT : LONG)[e - 4];
      }
      for (j = 2012; j <= 2026; j += narrow ? 4 : 2) {
        t = svgEl('text', { x: X(j), y: height - 8, 'text-anchor': 'middle', 'class': 'qc-axis' }, svg);
        t.textContent = String(j);
      }

      if (data.reference) {
        var ry = Y(data.reference.qubits);
        svgEl('line', { x1: m.left, x2: width - m.right, y1: ry, y2: ry, 'class': 'qc-ref' }, svg);
        t = svgEl('text', { x: m.left + 6, y: ry + 16, 'class': 'qc-ref-label' }, svg);
        t.textContent = narrow && data.reference.short ? data.reference.short : data.reference.label;
      }

      each(data.points, function (p) {
        var px = X(p.year);
        var py = Y(p.qubits);
        var dy = Number(p.dy) || 0;
        var left = p.side === 'left';
        var lx = left ? px - 11 : px + 11;
        var anchor = left ? 'end' : 'start';
        var link = svgEl('a', { href: p.link, target: '_blank', rel: 'noopener', tabindex: '-1' }, svg);
        svgEl('circle', { cx: px, cy: py, r: 6, 'class': 'qc-pt qc-pt-' + p.code }, link);
        var value = svgEl('text', { x: lx, y: py - 2 + dy, 'text-anchor': anchor, 'class': 'qc-pt-value' }, link);
        value.textContent = p.value;
        var who = svgEl('text', { x: lx, y: py + 14 + dy, 'text-anchor': anchor, 'class': 'qc-pt-who' }, link);
        who.textContent = narrow ? (p.chart_who_short || p.who_short || p.chart_who || p.who) : (p.chart_who || p.who);
      });

      plot.innerHTML = '';
      plot.appendChild(svg);
    }

    draw();
    return draw;
  }

  /* ---- 3. blueprint and topic sections --------------------------------------- */

  function initBlueprint(root) {
    var boxes = Array.prototype.slice.call(root.querySelectorAll('[data-qc-part]'));
    var panels = Array.prototype.slice.call(root.querySelectorAll('[data-qc-part-panel]'));
    if (!boxes.length || !panels.length) return;

    function select(id, reveal) {
      var shown = null;
      boxes.forEach(function (box) {
        var on = box.getAttribute('data-qc-part') === id;
        box.classList.toggle('is-active', on);
        box.setAttribute('aria-expanded', on ? 'true' : 'false');
      });
      panels.forEach(function (panel) {
        var on = panel.getAttribute('data-qc-part-panel') === id;
        panel.hidden = !on;
        if (on) shown = panel;
      });
      if (reveal && shown) {
        var top = shown.getBoundingClientRect().top;
        if (top > window.innerHeight - 160) {
          window.scrollTo({ top: top + window.pageYOffset - 80, behavior: reducedMotion() ? 'auto' : 'smooth' });
        }
      }
    }

    boxes.forEach(function (box) {
      box.setAttribute('role', 'button');
      box.addEventListener('click', function (event) {
        event.preventDefault();
        select(box.getAttribute('data-qc-part'), true);
      });
      box.addEventListener('keydown', function (event) {
        if (event.key === ' ') {
          event.preventDefault();
          box.click();
        }
      });
    });

    select(root.getAttribute('data-default') || boxes[0].getAttribute('data-qc-part'), false);
  }

  function initTopics() {
    var topics = Array.prototype.slice.call(document.querySelectorAll('section.topic'));
    if (!topics.length) return;
    var links = Array.prototype.slice.call(document.querySelectorAll('[data-qc-topic]'));
    var allLink = document.querySelector('[data-qc-topics-all]');
    topics[0].parentNode.classList.add('js-topics');

    function setOpen(topic, on) {
      topic.classList.toggle('is-open', on);
      var h = topic.querySelector('h2');
      if (h) h.setAttribute('aria-expanded', on ? 'true' : 'false');
    }

    function openTopic(id, scroll) {
      topics.forEach(function (t) {
        setOpen(t, t.id === id);
      });
      if (scroll) {
        var target = document.getElementById(id);
        if (target) {
          var top = target.getBoundingClientRect().top + window.pageYOffset - 72;
          window.scrollTo({ top: top, behavior: reducedMotion() ? 'auto' : 'smooth' });
        }
      }
    }

    function closeAll() {
      topics.forEach(function (t) {
        setOpen(t, false);
      });
    }

    links.forEach(function (link) {
      link.addEventListener('click', function (event) {
        event.preventDefault();
        var id = link.getAttribute('data-qc-topic');
        openTopic(id, true);
        if (window.history.replaceState) window.history.replaceState(null, '', '#' + id);
      });
    });

    topics.forEach(function (t) {
      var h = t.querySelector('h2');
      if (!h) return;
      h.setAttribute('tabindex', '0');
      h.setAttribute('role', 'button');
      h.setAttribute('aria-expanded', 'false');
      h.addEventListener('click', function () {
        if (t.classList.contains('is-open')) {
          closeAll();
        } else {
          openTopic(t.id, false);
          if (window.history.replaceState) window.history.replaceState(null, '', '#' + t.id);
        }
      });
      h.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          h.click();
        }
      });
    });

    if (allLink) {
      allLink.addEventListener('click', function (event) {
        event.preventDefault();
        var anyClosed = topics.some(function (t) {
          return !t.classList.contains('is-open');
        });
        topics.forEach(function (t) {
          setOpen(t, anyClosed);
        });
        allLink.textContent = anyClosed ? 'collapse all' : 'show all';
      });
    }

    var hash = window.location.hash.replace('#', '');
    var target = hash && document.getElementById(hash);
    if (target && target.classList.contains('topic')) openTopic(hash, true);
  }

  /* ---- 4. milestone filters ------------------------------------------------ */

  function initTimeline(root) {
    var items = root.querySelectorAll('.qc-tl-item');
    var groups = root.querySelectorAll('.qc-tl-year');
    var filters = root.querySelector('[data-qc-filters]');
    var chips = root.querySelectorAll('[data-qc-filter]');
    var more = root.querySelector('[data-qc-more]');
    var recentFrom = parseInt(root.getAttribute('data-recent-from'), 10) || 0;
    var kind = 'all';
    var showEarlier = false;

    function apply() {
      each(items, function (item) {
        var kindOK = kind === 'all' || item.getAttribute('data-kind') === kind;
        var yearOK = showEarlier || parseInt(item.getAttribute('data-year'), 10) >= recentFrom;
        item.hidden = !(kindOK && yearOK);
      });
      each(groups, function (group) {
        group.hidden = !group.querySelector('.qc-tl-item:not([hidden])');
      });
      each(chips, function (chip) {
        chip.setAttribute('aria-pressed', String(chip.getAttribute('data-qc-filter') === kind));
      });
      if (more) more.hidden = showEarlier;
    }

    each(chips, function (chip) {
      chip.addEventListener('click', function () {
        kind = chip.getAttribute('data-qc-filter');
        apply();
      });
    });
    if (more) {
      more.addEventListener('click', function () {
        showEarlier = true;
        apply();
      });
    }
    if (filters) filters.hidden = false;
    apply();
  }

  /* ---- start --------------------------------------------------------------- */

  function start() {
    var redraws = [];
    var budget = document.querySelector('[data-qc-budget]');
    var estimates = document.querySelector('[data-qc-estimates]');
    var timeline = document.querySelector('[data-qc-timeline]');
    var blueprint = document.querySelector('[data-qc-blueprint]');
    var redraw;

    if (budget && (redraw = initBudget(budget))) redraws.push(redraw);
    if (estimates && (redraw = initEstimates(estimates))) redraws.push(redraw);
    if (timeline) initTimeline(timeline);
    if (blueprint) initBlueprint(blueprint);
    initTopics();

    var lastWidth = window.innerWidth;
    var timer = null;
    window.addEventListener('resize', function () {
      if (window.innerWidth === lastWidth) return;
      lastWidth = window.innerWidth;
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        redraws.forEach(function (fn) {
          fn();
        });
      }, 150);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
