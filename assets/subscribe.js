/* DI Forum 구독 폼 — form.dif-sub 를 찾아 Apps Script 웹앱으로 전송 */
(function () {
  var cfg = window.DIF_CONFIG || {};
  var RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  document.querySelectorAll('form.dif-sub').forEach(function (f) {
    var msg = f.querySelector('.msg');
    function say(t, err) { msg.textContent = t; msg.className = 'msg' + (err ? ' err' : ''); }
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var d = {
        email: (f.email.value || '').trim().toLowerCase(),
        name: (f.name_.value || '').trim(),
        org: (f.org.value || '').trim(),
        website: f.website.value,               // honeypot
        consentPrivacy: f.c1.checked,
        consentMarketing: f.c2.checked,
        consentVersion: cfg.consentVersion || '',
        source: location.pathname
      };
      if (!RE.test(d.email)) return say('이메일 주소를 확인해 주세요.', true);
      if (!d.consentPrivacy || !d.consentMarketing) return say('두 가지 동의에 체크해 주세요.', true);
      if (!cfg.endpoint) return say('구독 시스템을 준비하고 있습니다. ' + (cfg.contact || '') + ' 로 메일 주시면 등록해 드립니다.', true);
      var btn = f.querySelector('button'); btn.disabled = true; say('등록 중입니다…');
      fetch(cfg.endpoint, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body: JSON.stringify(d) })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (j && j.ok) { f.reset(); say(j.message || '확인 메일을 보냈습니다. 메일의 [구독 확인] 버튼을 눌러야 구독이 완료됩니다.'); }
          else say((j && j.message) || '등록하지 못했습니다. 잠시 후 다시 시도해 주세요.', true);
        })
        .catch(function () { say('요청은 보냈지만 결과를 확인하지 못했습니다. 몇 분 안에 확인 메일이 오지 않으면 다시 시도해 주세요.', true); })
        .finally(function () { btn.disabled = false; });
    });
  });
})();
