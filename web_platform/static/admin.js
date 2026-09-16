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

function fmtDate(ts) {
  if (!ts) return '-';
  const d = new Date(ts * 1000);
  const p = n => String(n).padStart(2, '0');
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
}

/* ---------------- 上传（含覆盖确认 + 自动备份） ---------------- */
async function adminUpload(force) {
  const fileInput = $('#upFile');
  if (!fileInput.files.length) return toast('请选择文件', false);
  const fd = new FormData();
  fd.append('kind', $('#upKind').value);
  fd.append('subdir', $('#upSubdir').value.trim());
  fd.append('uploader', $('#upUploader').value.trim() || 'admin');
  fd.append('force', force ? 'true' : 'false');
  fd.append('file', fileInput.files[0]);
  const d = await adminApi('/api/admin/upload', {method: 'POST', body: fd});
  if (d.needToken) { $('#authCard').style.display = ''; return toast('请先输入访问口令', false); }

  if (d.exists) {
    // 同名覆盖确认：展示原上传人与修改时间，确认后自动备份
    const m = d.meta || {};
    const yes = await confirmModal('⚠️ 覆盖同名文件',
      '该文件已存在，原上传人：' + (m.uploader || '框架') +
      '，修改时间：' + fmtDate(m.modify_time) +
      '。确认将覆盖旧文件，系统自动备份历史版本。', true);
    if (yes) { $('#btnUpload').textContent = '⏳ 上传中…'; await adminUpload(true); $('#btnUpload').textContent = '⬆ 上传'; }
    return;
  }
  toast(d.msg || (d.ok ? '上传成功' : '上传失败'), d.ok);
  if (d.ok) fileInput.value = '';
}

/* ---------------- 用例包（zip）入库：三件套一次性写入 ---------------- */
async function adminUploadPackage() {
  const fileInput = $('#upPkgFile');
  if (!fileInput.files.length) return toast('请选择用例包 zip', false);
  const fd = new FormData();
  fd.append('uploader', $('#upPkgUploader').value.trim() || 'admin');
  fd.append('file', fileInput.files[0]);
  const btn = $('#btnUploadPkg');
  btn.textContent = '⏳ 入库中…'; btn.disabled = true;
  try {
    const d = await adminApi('/api/admin/upload_package', {method: 'POST', body: fd});
    if (d.needToken) { $('#authCard').style.display = ''; return toast('请先输入访问口令', false); }
    toast(d.msg || (d.ok ? '用例包已入库' : '入库失败'), d.ok);
    if (d.ok) fileInput.value = '';
  } finally {
    btn.textContent = '📦 上传用例包'; btn.disabled = false;
  }
}

/* ---------------- 初始化 ---------------- */
function adminInit() {
  renderSidebar('/admin');
  $('#btnUpload').addEventListener('click', () => adminUpload(false));
  $('#btnUploadPkg').addEventListener('click', adminUploadPackage);
  $('#btnToken').addEventListener('click', () => {
    localStorage.setItem('adminToken', $('#inToken').value.trim());
    toast('口令已保存到本机浏览器');
  });
}

document.addEventListener('DOMContentLoaded', adminInit);
