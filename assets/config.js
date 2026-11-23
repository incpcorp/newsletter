/* DI Forum 사이트 설정 — 구독 시스템(Google Apps Script) 배포 후 아래 주소만 채우면 됩니다.
   예) endpoint: "https://script.google.com/macros/s/AKfycbyJRVqFzi_PoTZZdJ-HGEoc_6c6ObRFGakJQ1hiPEL7rBE5he9i9ty8lLn_qcKO-Ufx/exec" */
window.DIF_CONFIG = {
  endpoint: "https://script.google.com/macros/s/AKfycbyJRVqFzi_PoTZZdJ-HGEoc_6c6ObRFGakJQ1hiPEL7rBE5he9i9ty8lLn_qcKO-Ufx/exec",
  contact: "incp@diforum.org",
  consentVersion: "2026-10-v1"
};

/* 방문 통계(2026-11-24 대표 승인): 본 페이지 경로와 들어오기 직전 사이트만 홈페이지(incpcorp.com) 기록 창구로 보낸다.
   쿠키를 쓰지 않고, IP 주소는 저장하지 않는다. 처리방침 11항. */
(function () {
  try {
    if (window.__difVisitSent || !/^(www\.)?diforum\.org$/.test(location.hostname)) return;
    window.__difVisitSent = true;
    var ref = "";
    try { ref = document.referrer ? new URL(document.referrer).hostname : ""; } catch (e) {}
    var d = JSON.stringify({ p: location.pathname, r: ref, n: false });
    var url = "https://www.incpcorp.com/api/track";
    if (!(navigator.sendBeacon && navigator.sendBeacon(url, new Blob([d], { type: "text/plain" })))) {
      fetch(url, { method: "POST", mode: "no-cors", keepalive: true, body: d }).catch(function () {});
    }
  } catch (e) {}
})();
