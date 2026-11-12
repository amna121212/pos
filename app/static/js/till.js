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

  async function submitCartForm(form) {
    var data = new FormData(form);
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
