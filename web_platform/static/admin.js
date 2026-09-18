/* 用例管理 · 上传（单文件 + 用例包 zip），覆盖确认 + 自动备份。
   文件列表/删除/重命名/批量操作/下载已按需求移除（文件浏览交给 git 与编辑器）。 */
'use strict';

function adminToken() { return localStorage.getItem('adminToken') || ''; }

function adminApi(url, opts) {
  opts = opts || {};
  opts.headers = Object.assign({'X-Admin-Token': adminToken()}, opts.headers || {});
  return fetch(url, opts).then(async res => {
    const data = await res.json().catch(() => ({ok: false, msg: '响应解析失败(' + res.status + ')'}));
    if (res.status === 401) data.needToken = true;
    return data;
  });
}

/* ---------------- 用例包（zip）入库：三件套一次性写入 ---------------- */
async function adminUploadPackage() {
  const fileInput = $('#upPkgFile');
  if (!fileInput.files.length) return toast('请选择用例包 zip', false);
  const fd = new FormData();
  fd.append('uploader', $('#upPkgUploader').value.trim() || 'admin');
  fd.append('file', fileInput.files[0]);
  const btn = $('#btnUploadPkg');
  btn.textContent = '入库中…'; btn.disabled = true;
  try {
    const d = await adminApi('/api/admin/upload_package', {method: 'POST', body: fd});
    if (d.needToken) { $('#authCard').style.display = ''; return toast('请先输入访问口令', false); }
    toast(d.msg || (d.ok ? '用例包已入库' : '入库失败'), d.ok);
    if (d.ok) fileInput.value = '';
  } finally {
    btn.textContent = '上传用例包'; btn.disabled = false;
  }
}

/* ---------------- 文件选择（自定义热区：紧凑胶囊按钮 + 已选文件名；
   原生 file 控件保留但视觉隐藏，上传逻辑仍读 input.files，行为不变） ---------------- */
function initFilePick() {
  document.querySelectorAll('.filepick-btn').forEach(btn => {
    const input = document.getElementById(btn.dataset.for);
    if (!input) return;
    btn.addEventListener('click', () => input.click());
    input.addEventListener('change', () => {
      const nameEl = document.querySelector('[data-name-for="' + input.id + '"]');
      if (!nameEl) return;
      const f = input.files && input.files[0];
      nameEl.textContent = f ? f.name : '未选择文件';
      nameEl.classList.toggle('has', !!f);
      nameEl.title = f ? f.name : '';
    });
  });
}

/* ---------------- 初始化 ----------------
   用例管理已并入 AppUI 自动化页（#panel-admin 面板），不再有独立页面：
   由 app.js 的 initRun() 调用 adminPanelInit() 完成绑定，本文件不再自启动。 */
function adminPanelInit() {
  if (!$('#btnUploadPkg')) return;   // 非 AppUI 页（无该面板）直接跳过
  initFilePick();
  $('#btnUploadPkg').addEventListener('click', adminUploadPackage);
  $('#btnToken').addEventListener('click', () => {
    localStorage.setItem('adminToken', $('#inToken').value.trim());
    toast('口令已保存到本机浏览器');
  });
}
