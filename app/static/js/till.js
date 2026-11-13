/* Till behaviour: no framework, no build step.
   Every basket control is a real form, so the till still works with JavaScript
   off. This file only swaps the cart panel in place instead of reloading. */
(function () {
  'use strict';

  var meta = document.querySelector('meta[name="csrf-token"]');
  var csrf = meta ? meta.getAttribute('content') : '';

  function panel() {
    return document.getElementById('cart-panel');
  }

  function swap(html) {
    var target = panel();
    if (target) {
      target.innerHTML = html;
    }
  }

  function money(value) {
    var amount = Number(value || 0);
    return 'Rs ' + amount.toLocaleString('en-PK', {
      minimumFractionDigits: 2, maximumFractionDigits: 2
    });
  }

  /* Keep the "amount received" hint in step with the total actually due, so a
     discounted bill never looks like it needs a manual figure. */
  function updateDue(payload) {
    var field = document.getElementById('amount_paid');
    if (!field || !payload || !payload.grand) { return; }
    field.placeholder = 'Full total — ' + money(payload.grand);
    field.setAttribute('data-due', payload.grand);
  }

  function discountFields() {
    return {
      kind: document.getElementById('discount_kind'),
      value: document.getElementById('discount_value')
    };
  }

  function setDiscountError(message) {
    var box = document.getElementById('discount-error');
    if (!box) { return; }
    if (!message) {
      box.hidden = true;
      box.textContent = '';
      return;
    }
    box.textContent = message;
    box.hidden = false;
  }

  /* Re-price the basket when the discount changes, so the totals block and the
     amount hint show the discounted figure before checkout. */
  var repriceTimer = null;
  function scheduleReprice() {
    if (repriceTimer) { window.clearTimeout(repriceTimer); }
    repriceTimer = window.setTimeout(reprice, 280);
  }

  async function reprice() {
    var fields = discountFields();
    if (!fields.value) { return; }
    var body = new FormData();
    body.append('_csrf', csrf);
    body.append('discount_kind', fields.kind ? fields.kind.value : 'percent');
    body.append('discount_value', fields.value.value || '');
    var response;
    try {
      response = await fetch('/pos/quote', {
        method: 'POST',
        body: body,
        headers: { 'X-Requested-With': 'fetch', 'X-CSRF-Token': csrf },
        credentials: 'same-origin'
      });
    } catch (error) {
      return;
    }
    var payload = await response.json().catch(function () { return null; });
    if (!response.ok || !payload || payload.ok !== true) {
      setDiscountError((payload && payload.error) || 'That discount cannot be applied.');
      return;
    }
    setDiscountError(null);
    swap(payload.html);
    updateDue(payload);
  }

  async function submitCartForm(form) {
    var data = new FormData(form);
    // Cart edits must keep the discount, otherwise the totals jump back up.
    var fields = discountFields();
    if (fields.kind) { data.append('discount_kind', fields.kind.value); }
    if (fields.value) { data.append('discount_value', fields.value.value || ''); }
    var response;
    try {
      response = await fetch(form.action, {
        method: 'POST',
        body: data,
        headers: { 'X-Requested-With': 'fetch', 'X-CSRF-Token': csrf },
        credentials: 'same-origin'
      });
    } catch (error) {
      return false;
    }
    if (!response.ok) {
      return false;
    }
    var payload = await response.json().catch(function () { return null; });
    if (!payload || !payload.html) {
      return false;
    }
    swap(payload.html);
    updateDue(payload);
    var counter = document.querySelector('.card > header .hint');
    if (counter) {
      counter.textContent = payload.lines + (payload.lines === 1 ? ' line' : ' lines');
    }
    return true;
  }

  document.addEventListener('submit', async function (event) {
    var form = event.target.closest('form[data-cart-form]');
    if (!form) {
      return;
    }
    event.preventDefault();
    var done = await submitCartForm(form);
    if (!done) {
      HTMLFormElement.prototype.submit.call(form);
    }
  });

  document.addEventListener('change', function (event) {
    var input = event.target.closest('[data-auto-submit]');
    if (input && input.form) {
      if (typeof input.form.requestSubmit === 'function') {
        input.form.requestSubmit();
      }
    }
  });

  function syncTableRow() {
    var type = document.getElementById('order_type');
    var row = document.getElementById('table-row');
    if (type && row) {
      row.style.display = type.value === 'dine_in' ? '' : 'none';
    }
  }

  var typeSelect = document.getElementById('order_type');
  if (typeSelect) {
    typeSelect.addEventListener('change', syncTableRow);
    syncTableRow();
  }

  // A discount reprices the basket live, so checkout never asks for a figure
  // the cashier has to work out by hand.
  var discountInputs = discountFields();
  if (discountInputs.value) {
    discountInputs.value.addEventListener('input', scheduleReprice);
  }
  if (discountInputs.kind) {
    discountInputs.kind.addEventListener('change', scheduleReprice);
  }
  (function initialiseDue() {
    var field = document.getElementById('amount_paid');
    var total = document.querySelector('#cart-panel .totals .grand .num');
    if (field && total) {
      field.placeholder = 'Full total — ' + total.textContent.trim();
    }
  })();

  var scan = document.getElementById('scan');
  if (scan) {
    scan.focus();
    document.addEventListener('keydown', function (event) {
      if (event.key === 'F2' || (event.key === '/' && event.target.tagName !== 'INPUT')) {
        event.preventDefault();
        scan.focus();
        scan.select();
      }
    });
    scan.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        scan.form.submit();
      }
    });
  }
})();
