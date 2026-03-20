function show(n, btn) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.sw-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('s' + n).classList.add('active');
  if (btn) {
    btn.classList.add('active');
  } else {
    document.querySelectorAll('.sw-btn')[n - 1].classList.add('active');
  }
  window.scrollTo(0, 0);
}