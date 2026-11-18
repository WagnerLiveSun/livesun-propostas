(() => {
  'use strict';
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#sales-nav');
  if (toggle && nav) {
    const mobile = window.matchMedia('(max-width: 700px)');
    const setOpen = (open) => {
      toggle.setAttribute('aria-expanded', String(open));
      nav.dataset.collapsed = String(mobile.matches && !open);
    };
    toggle.hidden = false;
    setOpen(false);
    toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
    nav.addEventListener('click', (event) => {
      if (event.target.closest('a')) setOpen(false);
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
        setOpen(false);
        toggle.focus();
      }
    });
    mobile.addEventListener('change', () => setOpen(false));
  }
  const error = document.querySelector('#cadastro-erro');
  if (error) error.focus();
})();