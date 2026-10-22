/* Barra lateral: recolher (só ícones) e grupos com toggle.
   Aberta, cada grupo abre e fecha no lugar. Recolhida, o grupo abre ao lado do ícone
   e só um fica aberto por vez; clicar fora fecha. */
(function () {
  var app = document.getElementById('app');
  var nav = document.getElementById('menu-lateral');
  if (!app || !nav) return;
  var grupos = nav.querySelectorAll('details.nav-toggle');

  function recolhida() {
    return app.classList.contains('lateral-recolhida') && window.matchMedia('(min-width: 901px)').matches;
  }

  function posicionar(det) {
    var sub = det.querySelector('.nav-sub');
    var topo = det.querySelector('summary').getBoundingClientRect().top;
    sub.style.top = Math.max(64, Math.min(topo, window.innerHeight - sub.offsetHeight - 8)) + 'px';
  }

  function fecharOutros(atual) {
    grupos.forEach(function (d) { if (d !== atual) d.open = false; });
  }

  grupos.forEach(function (det) {
    det.addEventListener('toggle', function () {
      if (!recolhida() || !det.open) return;
      fecharOutros(det);
      posicionar(det);
    });
  });

  document.addEventListener('click', function (ev) {
    if (recolhida() && !nav.contains(ev.target)) fecharOutros(null);
    var menu = document.querySelector('.menu-usuario');
    if (menu && menu.open && !menu.contains(ev.target)) menu.open = false;
  });

  window.alternarLateral = function () {
    var fechar = !app.classList.contains('lateral-recolhida');
    app.classList.toggle('lateral-recolhida', fechar);
    try { localStorage.setItem('crm_lateral_recolhida', fechar ? '1' : '0'); } catch (e) {}
    // Recolhida: nada fica aberto. Aberta de novo: volta só o grupo da página atual.
    grupos.forEach(function (d) { d.open = !fechar && d.dataset.abertoInicial === '1'; });
  };

  // Recolhida, a página começa sem grupo aberto ao lado.
  if (recolhida()) fecharOutros(null);
})();
