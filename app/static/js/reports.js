/* Reports page.
 *
 * One renderer, one JSON endpoint. The URL is the source of truth for the filter
 * state: the shell renders from a bootstrap copy, every change pushes the new
 * state into the query string, and back/forward re-reads it. No filter change
 * reloads the page.
 */
(function () {
  'use strict';

  var bootEl = document.getElementById('report-bootstrap');
  if (!bootEl) { return; }
  var boot = JSON.parse(bootEl.textContent);
  var state = Object.assign({}, boot.raw);
  var currentBusinessId = boot.businessId;
  var labels = boot.labels || {};
  var inflight = null;

  var FILTER_IDS = {
    'filter-branch': 'branch',
    'filter-from': 'from',
    'filter-to': 'to',
    'filter-group': 'group',
    'filter-status': 'status',
    'filter-payment': 'payment',
    'filter-category': 'category',
    'filter-employee': 'employee',
    'filter-supplier': 'supplier',
    'filter-limit': 'limit'
  };
  var PARAM_ORDER = ['from', 'to', 'branch', 'group', 'status', 'category', 'payment', 'employee', 'supplier', 'compare', 'limit'];

  // ---------------------------------------------------------------- helpers

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function toNumber(value) {
    var n = parseFloat(String(value == null ? 0 : value));
    return isNaN(n) ? 0 : n;
  }

  function money(value) {
    var n = toNumber(value);
    var sign = n < 0 ? '-' : '';
    return sign + 'Rs ' + Math.abs(n).toLocaleString('en-PK', {
      minimumFractionDigits: 2, maximumFractionDigits: 2
    });
  }

  function amount(value) {
    var n = toNumber(value);
    return Math.abs(n).toLocaleString('en-PK', { maximumFractionDigits: 0 });
  }

  function qty(value) {
    var n = toNumber(value);
    var rounded = Math.round(n * 1000) / 1000;
    return rounded.toLocaleString('en-PK', { maximumFractionDigits: 3 });
  }

  function percent(value) {
    if (value === null || value === undefined) { return '<span class="faint">–</span>'; }
    var n = toNumber(value);
    var cls = n > 0 ? 'delta-up' : (n < 0 ? 'delta-down' : 'faint');
    var arrow = n > 0 ? '▲' : (n < 0 ? '▼' : '•');
    return '<span class="' + cls + '">' + arrow + ' ' + Math.abs(n).toFixed(1) + '%</span>';
  }

  function shortDate(iso) {
    var parts = String(iso || '').slice(0, 10).split('-');
    if (parts.length !== 3) { return esc(iso); }
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return parts[2] + ' ' + months[parseInt(parts[1], 10) - 1];
  }

  function emptyState(title, detail) {
    return '<div class="empty"><strong>' + esc(title) + '</strong>' + esc(detail || '') + '</div>';
  }

  function statCards(items) {
    return '<div class="stats">' + items.map(function (item) {
      return '<div class="stat"><div class="k">' + esc(item.label) + '</div>' +
        '<div class="v' + (item.small ? ' small' : '') + '">' + item.value + '</div>' +
        '<div class="n">' + (item.sub || '') + '</div></div>';
    }).join('') + '</div>';
  }

  function table(headers, rows, options) {
    options = options || {};
    var head = headers.map(function (header) {
      return '<th' + (header.num ? ' class="num"' : '') + '>' + esc(header.label) + '</th>';
    }).join('');
    var body = rows.map(function (row) {
      return '<tr>' + row.map(function (cell, index) {
        return '<td' + (headers[index] && headers[index].num ? ' class="num"' : '') + '>' + cell + '</td>';
      }).join('') + '</tr>';
    }).join('');
    return '<div class="table-wrap' + (options.scroll ? ' scroll-y' : '') + '"><table><thead><tr>' +
      head + '</tr></thead><tbody>' + body + '</tbody></table></div>';
  }

  function columnChart(rows, valueKey, labelKey) {
    if (!rows.length) { return ''; }
    var max = rows.reduce(function (top, row) { return Math.max(top, toNumber(row[valueKey])); }, 0) || 1;
    var bars = rows.map(function (row) {
      var value = toNumber(row[valueKey]);
      var height = Math.max(2, Math.round(value / max * 100));
      return '<div class="col" title="' + esc(row[labelKey]) + ': ' + money(row[valueKey]) + '">' +
        '<div class="col-track"><div class="col-fill" style="height:' + height + '%"></div></div>' +
        '<div class="col-label">' + esc(row[labelKey]) + '</div></div>';
    }).join('');
    return '<div class="cols-chart">' + bars + '</div>';
  }

  function barList(rows, labelKey, valueKey, formatter) {
    if (!rows.length) { return ''; }
    var format = formatter || money;
    var max = rows.reduce(function (top, row) { return Math.max(top, toNumber(row[valueKey])); }, 0) || 1;
    return '<div class="bar-list">' + rows.map(function (row) {
      var width = Math.max(1, Math.round(toNumber(row[valueKey]) / max * 100));
      return '<div class="bar-row"><span class="bar-name" title="' + esc(row[labelKey]) + '">' +
        esc(row[labelKey]) + '</span><span class="bar-track"><span class="bar-fill" style="width:' +
        width + '%"></span></span><span class="val">' + format(row[valueKey]) + '</span></div>';
    }).join('') + '</div>';
  }

  // ---------------------------------------------------------------- sections

  var renderers = {
    overview: function (data) {
      var current = data.current || {};
      var deltas = data.deltas || {};
      var showDelta = state.compare === '1';
      return statCards([
        { label: 'Net sales', value: money(current.net_sales), sub: showDelta ? 'vs previous ' + percent(deltas.net_sales) : 'Excluding tax' },
        { label: 'Paid orders', value: amount(current.orders), sub: showDelta ? 'vs previous ' + percent(deltas.orders) : 'In period' },
        { label: 'Average order', value: money(current.average_order_value), sub: showDelta ? 'vs previous ' + percent(deltas.average_order_value) : 'Net of tax' },
        { label: 'Items sold', value: amount(current.items_sold), sub: (current.items_per_order || 0) + ' per order' },
        { label: 'Tax', value: money(current.tax), sub: 'Collected' },
        { label: 'Discounts', value: money(current.discount), sub: 'Given' }
      ]);
    },

    daily: function (rows) {
      if (!rows.length) { return emptyState('No sales in this period', 'Widen the dates or clear a filter.'); }
      var total = rows.reduce(function (sum, row) { return sum + toNumber(row.net_sales); }, 0);
      return columnChart(rows, 'net_sales', 'label') +
        '<div class="report-foot">' + rows.length + ' trading days · ' + money(total) + ' net</div>';
    },

    weekly: function (rows) {
      if (!rows.length) { return emptyState('No weekly figures', 'Nothing to aggregate for these dates.'); }
      return barList(rows, 'label', 'net_sales');
    },

    monthly: function (rows) {
      if (!rows.length) { return emptyState('No monthly figures', 'Nothing to aggregate for these dates.'); }
      return barList(rows, 'label', 'net_sales');
    },

    branches: function (rows) {
      if (!rows.length) { return emptyState('No branch activity', 'No paid orders at these branches in the period.'); }
      return table(
        [{ label: 'Branch' }, { label: 'Orders', num: true }, { label: 'Net sales', num: true },
         { label: 'Average', num: true }, { label: 'Gross', num: true }],
        rows.map(function (row) {
          return [esc(row.code) + ' <span class="faint">' + esc(row.name) + '</span>',
                  amount(row.orders), money(row.net_sales), money(row.average_order_value), money(row.gross)];
        })
      );
    },

    products: function (rows) {
      if (!rows.length) { return emptyState('No products sold', 'No paid order lines match these filters.'); }
      return table(
        [{ label: 'Product' }, { label: 'Qty sold', num: true }, { label: 'Revenue', num: true }],
        rows.map(function (row) {
          return [esc(row.name) + ' <span class="faint mono">' + esc(row.sku) + '</span>',
                  qty(row.quantity), money(row.revenue)];
        })
      );
    },

    categories: function (rows) {
      if (!rows.length) { return emptyState('No category sales', 'No paid lines match these filters.'); }
      return barList(rows, 'name', 'revenue');
    },

    payments: function (rows) {
      if (!rows.length) { return emptyState('No captured payments', 'No payment matches these filters.'); }
      return table(
        [{ label: 'Method' }, { label: 'Payments', num: true }, { label: 'Amount', num: true }, { label: 'Share', num: true }],
        rows.map(function (row) {
          return [esc(row.label), amount(row.payments), money(row.amount), row.share + '%'];
        })
      );
    },

    cancelled: function (data) {
      var parts = [
        statCards([
          { label: 'Cancelled orders', value: amount(data.cancelled_orders), sub: money(data.cancelled_value) + ' of value' },
          { label: 'Refunds', value: amount((data.returns || []).reduce(function (s, r) { return s + toNumber(r.amount); }, 0)),
            sub: ((data.returns || [])[0] ? data.returns[0].count : 0) + ' posted' }
        ])
      ];
      if ((data.unsettled || []).length) {
        parts.push('<h3 class="sub-head">Unsettled</h3>' + table(
          [{ label: 'Status' }, { label: 'Orders', num: true }, { label: 'Value', num: true }],
          data.unsettled.map(function (row) { return [esc(row.status.replace('_', ' ')), amount(row.orders), money(row.value)]; })
        ));
      }
      if ((data.recent_returns || []).length) {
        parts.push('<h3 class="sub-head">Recent refunds</h3>' + table(
          [{ label: 'Return' }, { label: 'Type' }, { label: 'Amount', num: true }],
          data.recent_returns.map(function (row) {
            return ['<span class="mono">' + esc(row.return_number) + '</span>', esc(row.return_type), money(row.amount)];
          })
        ));
      } else if (data.cancelled_orders === 0) {
        parts.push(emptyState('Nothing cancelled or refunded', 'Clean period.'));
      }
      return parts.join('');
    },

    cashiers: function (rows) {
      if (!rows.length) { return emptyState('No cashier activity', 'No paid orders carry a shift in this period.'); }
      return table(
        [{ label: 'Cashier' }, { label: 'Branch' }, { label: 'Orders', num: true },
         { label: 'Net sales', num: true }, { label: 'Average', num: true }, { label: 'Discounts', num: true }],
        rows.map(function (row) {
          return [esc(row.name), esc(row.branch), amount(row.orders), money(row.net_sales),
                  money(row.average_order_value), money(row.discounts)];
        })
      );
    },

    stock: function (data) {
      var html = '';
      if ((data.by_type || []).length) {
        html += table(
          [{ label: 'Movement' }, { label: 'Rows', num: true }, { label: 'Net qty', num: true }],
          data.by_type.map(function (row) {
            return [esc(row.movement_type.replace(/_/g, ' ')), amount(row.movements), qty(row.delta)];
          })
        );
      }
      if ((data.top_consumed || []).length) {
        html += '<h3 class="sub-head">Most consumed</h3>' + table(
          [{ label: 'Item' }, { label: 'Consumed', num: true }],
          data.top_consumed.map(function (row) {
            return [esc(row.name) + ' <span class="faint mono">' + esc(row.sku) + '</span>',
                    qty(Math.abs(toNumber(row.delta))) + ' ' + esc(row.unit)];
          })
        );
      }
      return html || emptyState('No stock movement', 'Nothing consumed or received in this period.');
    },

    low_stock: function (rows) {
      if (!rows.length) { return emptyState('Nothing below the reorder level', 'At the selected branch.'); }
      return table(
        [{ label: 'Item' }, { label: 'On hand', num: true }, { label: 'Reorder at', num: true }],
        rows.map(function (row) {
          return [esc(row.name) + ' <span class="faint mono">' + esc(row.sku) + '</span>',
                  qty(row.quantity) + ' ' + esc(row.unit), qty(row.reorder_level)];
        })
      );
    },

    purchases: function (data) {
      var html = statCards([
        { label: 'Goods received', value: amount(data.received_count), sub: 'In this period' },
        { label: 'Suppliers with orders', value: amount((data.by_supplier || []).length), sub: 'Raised in period' }
      ]);
      if ((data.by_supplier || []).length) {
        html += table(
          [{ label: 'Supplier' }, { label: 'Orders', num: true }, { label: 'Value', num: true }],
          data.by_supplier.map(function (row) {
            return [esc(row.name), amount(row.orders), money(row.value)];
          })
        );
      }
      if ((data.recent || []).length) {
        html += '<h3 class="sub-head">Recent purchase orders</h3>' + table(
          [{ label: 'PO' }, { label: 'Supplier' }, { label: 'Status' }, { label: 'Value', num: true }],
          data.recent.map(function (row) {
            return ['<span class="mono">' + esc(row.po_number) + '</span>', esc(row.supplier),
                    '<span class="badge">' + esc(row.status) + '</span>', money(row.value)];
          })
        );
      } else if (!(data.by_supplier || []).length) {
        html += emptyState('No purchase orders', 'None raised in this period.');
      }
      return html;
    },

    discounts: function (data) {
      var html = statCards([
        { label: 'Discounted orders', value: amount(data.discounted_orders), sub: 'In period' },
        { label: 'Total discount', value: money(data.total_discount), sub: 'Given away' },
        { label: 'Average discount', value: money(data.average_discount), sub: 'Per discounted order' }
      ]);
      if ((data.top_discounts || []).length) {
        html += table(
          [{ label: 'Order' }, { label: 'Branch' }, { label: 'Discount', num: true }],
          data.top_discounts.map(function (row) {
            return ['<span class="mono">' + esc(row.order_number) + '</span>', esc(row.branch), money(row.amount)];
          })
        );
      }
      return html;
    },

    operations: function (data) {
      var html = '';
      if ((data.by_order_type || []).length) {
        html += table(
          [{ label: 'Order type' }, { label: 'Orders', num: true }, { label: 'Gross', num: true }],
          data.by_order_type.map(function (row) {
            return [esc(String(row.order_type).replace(/_/g, ' ')), amount(row.orders), money(row.gross)];
          })
        );
      }
      if ((data.by_hour || []).length) {
        html += '<h3 class="sub-head">Busiest hours</h3>' + barList(
          data.by_hour.map(function (row) {
            return { label: String(row.hour).padStart(2, '0') + ':00', orders: row.orders };
          }), 'label', 'orders', amount
        );
      }
      if ((data.by_weekday || []).length) {
        html += '<h3 class="sub-head">Busiest days</h3>' + barList(data.by_weekday, 'weekday', 'orders', amount);
      }
      html += '<div class="report-foot">' + amount(data.kitchen_tickets) + ' kitchen tickets in period</div>';
      return html;
    },

    provenance: function (data, extra) {
      var split = data || {};
      var mix = extra || [];
      var html = '<p class="note mb0">Synthetic history is generated coursework data, not real trading. ' +
        esc(split.synthetic) + ' of ' + (toNumber(split.synthetic) + toNumber(split.live)) +
        ' paid orders in this period come from it; ' + esc(split.live) + ' were taken at this till.</p>';
      if (mix.length) {
        html += '<h3 class="sub-head">Order status mix</h3>' + table(
          [{ label: 'Status' }, { label: 'Orders', num: true }, { label: 'Value', num: true }],
          mix.map(function (row) {
            return [esc(String(row.status).replace(/_/g, ' ')), amount(row.orders), money(row.value)];
          })
        );
      }
      return html;
    }
  };

  // ---------------------------------------------------------------- rendering

  function sectionNode(name) {
    return document.querySelector('[data-section="' + name + '"]');
  }

  function renderSections(sections) {
    Object.keys(sections).forEach(function (name) {
      if (name === 'status_mix') { return; }
      var node = sectionNode(name);
      if (!node) { return; }
      var target = node.querySelector('[data-role="content"]');
      if (!target) { return; }
      var renderer = renderers[name];
      if (!renderer) { target.innerHTML = emptyState('Not available'); return; }
      try {
        var html = (name === 'provenance')
          ? renderer(sections[name], sections.status_mix)
          : renderer(sections[name]);
        target.innerHTML = html || emptyState('No records', 'Nothing matches the active filters.');
      } catch (error) {
        target.innerHTML = '<div class="report-inline-error">Could not draw this panel.</div>';
        if (window.console) { console.error(name, error); }
      }
    });
    var caption = document.querySelector('[data-section="daily"] [data-role="caption"]');
    if (caption) { caption.textContent = labels.period || ''; }
    var overviewPeriod = document.querySelector('[data-section="overview"] [data-role="period"]');
    if (overviewPeriod) { overviewPeriod.textContent = labels.period || ''; }
  }

  function setHeading() {
    var heading = document.getElementById('report-heading');
    if (heading) {
      heading.textContent = [labels.business, labels.branch, labels.period].filter(Boolean).join(' · ');
    }
  }

  function showStatus(message) {
    var box = document.getElementById('report-status');
    var text = document.getElementById('report-status-text');
    if (!box) { return; }
    if (!message) { box.hidden = true; return; }
    text.textContent = message;
    box.hidden = false;
  }

  function showError(message) {
    var box = document.getElementById('report-error');
    if (!box) { return; }
    if (!message) { box.hidden = true; return; }
    document.getElementById('report-error-text').textContent = message;
    box.hidden = false;
  }

  // ---------------------------------------------------------------- transport

  function queryFromState() {
    var params = new URLSearchParams();
    PARAM_ORDER.forEach(function (key) {
      var value = state[key];
      if (value === undefined || value === null || value === '') {
        if (key === 'compare') { params.set('compare', '0'); }
        return;
      }
      params.set(key, value);
    });
    return params;
  }

  function currentUrl(push) {
    var url = window.location.pathname + '?' + queryFromState().toString();
    if (push && url !== window.location.pathname + window.location.search) {
      window.history.pushState({ reports: true }, '', url);
    } else if (!push) {
      window.history.replaceState({ reports: true }, '', url);
    }
  }

  async function load(options) {
    options = options || {};
    if (inflight) { inflight.abort(); }
    inflight = new AbortController();
    showError(null);
    showStatus('Updating ' + (labels.period || 'reports') + '…');
    document.getElementById('report-body').classList.add('is-loading');
    try {
      var response = await fetch('/reports/api/data?' + queryFromState().toString(), {
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin',
        signal: inflight.signal
      });
      var payload = await response.json().catch(function () { return null; });
      if (!response.ok || !payload || payload.ok !== true) {
        var detail = (payload && (payload.error || payload.detail)) || ('HTTP ' + response.status);
        throw new Error(detail);
      }
      if (payload.labels) { labels = payload.labels; }
      setHeading();
      renderSections(payload.sections || {});
      if (options.push !== false) { currentUrl(true); }
      showStatus(null);
    } catch (error) {
      if (error.name === 'AbortError') { return; }
      showStatus(null);
      showError(error.message || 'The request failed.');
    } finally {
      document.getElementById('report-body').classList.remove('is-loading');
    }
  }

  function applyFromForm(push) {
    Object.keys(FILTER_IDS).forEach(function (id) {
      var element = document.getElementById(id);
      if (element) { state[FILTER_IDS[id]] = element.value; }
    });
    var compare = document.getElementById('filter-compare');
    if (compare) { state.compare = compare.checked ? '1' : '0'; }
    if (state.from > state.to) {
      var swap = state.from; state.from = state.to; state.to = swap;
      document.getElementById('filter-from').value = state.from;
      document.getElementById('filter-to').value = state.to;
    }
    if (push === false) { currentUrl(false); }
    load({ push: push !== false });
  }

  function fillFormFromState() {
    Object.keys(FILTER_IDS).forEach(function (id) {
      var element = document.getElementById(id);
      if (element) { element.value = state[FILTER_IDS[id]] || element.options[0].value; }
    });
    var compare = document.getElementById('filter-compare');
    if (compare) { compare.checked = state.compare === '1'; }
  }

  function stateFromUrl() {
    var params = new URLSearchParams(window.location.search);
    var next = {};
    PARAM_ORDER.forEach(function (key) {
      if (params.has(key)) { next[key] = params.get(key); }
    });
    return Object.assign({}, boot.raw, next);
  }

  // ----------------------------------------------------------- context switch

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function optionsHtml(rows, valueKey, labelKey, placeholder, selected) {
    var html = placeholder === null ? '' : '<option value="">' + esc(placeholder) + '</option>';
    rows.forEach(function (row) {
      var value = String(row[valueKey]);
      html += '<option value="' + value + '"' +
        (value === String(selected == null ? '' : selected) ? ' selected' : '') + '>' +
        esc(row[labelKey]) + '</option>';
    });
    return html;
  }

  function syncTopbarBranches(rows, selectedId) {
    var select = document.getElementById('branch-select');
    if (!select) { return; }
    select.innerHTML = rows.map(function (branch) {
      return '<option value="' + branch.id + '"' + (branch.id === selectedId ? ' selected' : '') + '>' +
        esc(branch.code) + ' &middot; ' + esc(branch.name) + '</option>';
    }).join('');
    select.disabled = rows.length < 2;
  }

  function rebuildBranchFilter(rows, value) {
    var select = document.getElementById('filter-branch');
    if (!select) { return; }
    select.innerHTML = '<option value="all">All branches</option>' + rows.map(function (branch) {
      return '<option value="' + branch.id + '">' + esc(branch.code) + ' &middot; ' + esc(branch.name) + '</option>';
    }).join('');
    select.value = value || 'all';
  }

  /* Apply the picker, then redraw this page instead of reloading it. */
  function postContext(fields) {
    var body = new FormData();
    body.append('_csrf', csrfToken());
    Object.keys(fields).forEach(function (key) {
      if (fields[key] !== undefined && fields[key] !== null && fields[key] !== '') {
        body.append(key, fields[key]);
      }
    });
    return fetch('/context', {
      method: 'POST',
      body: body,
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'fetch', 'Accept': 'application/json' }
    }).then(function (response) {
      return response.json().then(function (payload) {
        if (!response.ok || !payload || payload.ok !== true) {
          throw new Error((payload && payload.error) || ('HTTP ' + response.status));
        }
        return payload;
      });
    });
  }

  /* A new tenant invalidates every record filter that belonged to the old one. */
  function afterBusinessSwitch(payload) {
    var brand = document.querySelector('.brand span');
    if (brand && payload.business) { brand.textContent = payload.business.name; }
    state.branch = 'all';
    state.category = '';
    state.payment = '';
    state.employee = '';
    state.supplier = '';
    syncTopbarBranches(payload.branches || [], payload.branch ? payload.branch.id : null);
    return fetch('/reports/api/options', {
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    }).then(function (response) {
      return response.json();
    }).then(function (options) {
      if (!options || options.ok !== true) { return; }
      rebuildBranchFilter(options.branches || [], 'all');
      var category = document.getElementById('filter-category');
      if (category) {
        category.innerHTML = optionsHtml(options.categories || [], 'id', 'name', 'All categories', '');
      }
      var payment = document.getElementById('filter-payment');
      if (payment) {
        payment.innerHTML = optionsHtml(options.payment_methods || [], 'id', 'label', 'All methods', '');
      }
      var employee = document.getElementById('filter-employee');
      if (employee) {
        employee.innerHTML = optionsHtml(options.employees || [], 'id', 'name', 'Everyone', '');
      }
      var supplier = document.getElementById('filter-supplier');
      if (supplier) {
        supplier.innerHTML = optionsHtml(options.suppliers || [], 'id', 'name', 'All suppliers', '');
      }
      fillFormFromState();
    });
  }

  /* The top-bar Apply button: one request for restaurant and branch together. */
  function wireContextSwitchers() {
    var form = document.querySelector('form[data-context-form]');
    if (!form) { return; }
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var businessSelect = document.getElementById('business-select');
      var branchSelect = document.getElementById('branch-select');
      var nextBusiness = businessSelect ? Number(businessSelect.value) : currentBusinessId;
      var changedBusiness = nextBusiness !== Number(currentBusinessId);

      showError(null);
      showStatus('Switching context…');
      postContext({
        business_id: businessSelect ? businessSelect.value : '',
        branch_id: branchSelect ? branchSelect.value : ''
      })
        .then(function (payload) {
          currentBusinessId = payload.business ? payload.business.id : currentBusinessId;
          if (changedBusiness) {
            return afterBusinessSwitch(payload).then(function () { load({ push: true }); });
          }
          syncTopbarBranches(payload.branches || [], payload.branch ? payload.branch.id : null);
          return load({ push: true });
        })
        .catch(function (error) {
          showStatus(null);
          showError(error.message || 'The context could not be changed.');
        });
    });
  }

  // ---------------------------------------------------------------- wiring

  function wire() {
    Object.keys(FILTER_IDS).forEach(function (id) {
      var element = document.getElementById(id);
      if (!element) { return; }
      element.addEventListener('change', function () { applyFromForm(true); });
    });
    var compare = document.getElementById('filter-compare');
    if (compare) { compare.addEventListener('change', function () { applyFromForm(true); }); }

    var apply = document.getElementById('filter-apply');
    if (apply) { apply.addEventListener('click', function () { applyFromForm(true); }); }

    ['report-filters', 'report-filters-2'].forEach(function (formId) {
      var form = document.getElementById(formId);
      if (form) {
        form.addEventListener('submit', function (event) {
          event.preventDefault();
          applyFromForm(true);
        });
      }
    });

    var reset = document.getElementById('report-reset');
    if (reset) {
      reset.addEventListener('click', function (event) {
        event.preventDefault();
        state = Object.assign({}, boot.raw, {
          from: boot.raw.from, to: boot.raw.to, branch: 'all',
          category: '', payment: '', employee: '', supplier: '',
          status: 'paid', group: 'day', compare: '1', limit: '15'
        });
        fillFormFromState();
        currentUrl(true);
        load({ push: false });
      });
    }

    // Switching restaurant is a tenancy change, so it is a real POST + navigation.
    var business = document.getElementById('filter-business');
    if (business) {
      business.addEventListener('change', function () {
        var params = new URLSearchParams();
        ['from', 'to', 'group', 'status', 'compare', 'limit'].forEach(function (key) {
          if (state[key]) { params.set(key, state[key]); }
        });
        params.set('branch', 'all');
        var form = document.createElement('form');
        form.method = 'post';
        form.action = '/business/' + business.value;
        var csrf = document.querySelector('meta[name="csrf-token"]');
        var token = document.createElement('input');
        token.type = 'hidden';
        token.name = '_csrf';
        token.value = csrf ? csrf.getAttribute('content') : '';
        var next = document.createElement('input');
        next.type = 'hidden';
        next.name = 'next';
        next.value = '/reports?' + params.toString();
        form.appendChild(token);
        form.appendChild(next);
        document.body.appendChild(form);
        form.submit();
      });
    }

    window.addEventListener('popstate', function () {
      state = stateFromUrl();
      fillFormFromState();
      load({ push: false });
    });

    wireContextSwitchers();
  }

  // ---------------------------------------------------------------- start

  state = stateFromUrl();
  fillFormFromState();
  setHeading();
  renderSections(boot.sections || {});
  currentUrl(false);
  wire();
})();
