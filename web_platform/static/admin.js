/* 管理后台 · 方案A：统一列表（类型筛选/上传人/受保护置灰）、批量操作、覆盖确认+自动备份 */
'use strict';

let ADMIN_FILES = [];     // 统一文件列表
let ADMIN_IS_ADMIN = true;
let PENDING_OVERWRITE = null;  // 覆盖确认时暂存的上传参数

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

/* ---------------- 列表 ---------------- */
async function adminLoadFiles() {
  const d = await adminApi('/api/admin/files');
  if (d.needToken) { $('#authCard').style.display = ''; toast('请先输入访问口令', false); return; }
  if (!d.ok) return toast(d.msg || '加载失败', false);
  ADMIN_FILES = d.files || [];
  ADMIN_IS_ADMIN = d.is_admin !== false;
  if (d.auth === 'off') $('#authCard').style.display = 'none';
  else $('#authCard').style.display = '';
  const pageY = window.scrollY;
  adminRenderList();
  window.scrollTo(0, pageY);
  adminLoadSubdirs();
}

function adminFiltered() {
  const t = $('#typeFilter').value;
  return t ? ADMIN_FILES.filter(f => f.file_type === t) : ADMIN_FILES.slice();
}

function adminRenderList() {
  const files = adminFiltered();
  $('#fileCount').textContent = '· 共 ' + files.length + ' 个';
  const tb = $('#fileList');
  // 保持滚动位置：页面级 + 列表容器内（筛选/重渲染不打断操作）
  const pageY = window.scrollY;
  const wrap = tb.closest('.tblwrap');
  const listY = wrap ? wrap.scrollTop : 0;
  const restore = () => {
    window.scrollTo(0, pageY);
    if (wrap) wrap.scrollTop = listY;
  };
  if (!files.length) {
    tb.innerHTML = '<tr><td colspan="7"><div class="empty">该类型下暂无文件</div></td></tr>';
    restore();
    return;
  }
  tb.innerHTML = files.map(f => {
    const protectedOps = '<span class="muted" title="框架公共文件，仅管理员可操作" style="cursor:not-allowed">🔒 受保护</span>';
    const ops = f.is_protected
      ? protectedOps
      : '<a class="btn ghost mini" style="text-decoration:none" href="/api/admin/download?path=' + encodeURIComponent(f.path) + '">下载</a>' +
        '<button class="ghost mini admin-rename" data-path="' + esc(f.path) + '">重命名</button>' +
        '<button class="mini danger-ghost admin-del" data-path="' + esc(f.path) + '">删除</button>';
    return '<tr>' +
      '<td><input type="checkbox" class="ck-file" data-path="' + esc(f.path) + '"' +
      (f.is_protected ? ' title="框架公共文件，仅管理员可操作"' : '') + '></td>' +
      '<td><b class="admin-file-path" title="' + esc(f.path) + '">' + esc(f.path) + '</b></td>' +
      '<td>' + esc(f.type_label) + (f.is_protected ? ' <span class="muted" title="框架公共文件，仅管理员可操作">🔒</span>' : '') + '</td>' +
      '<td class="muted">' + (f.size / 1024).toFixed(1) + ' KB</td>' +
      '<td class="muted">' + fmtDate(f.mtime) + '</td>' +
      '<td class="muted">' + esc(f.uploader) + '</td>' +
      '<td><div class="ops">' + ops + '</div></td></tr>';
  }).join('');
  restore();
}

function adminSelected() {
  return [...document.querySelectorAll('#fileList .ck-file:checked')].map(c => c.dataset.path);
}

/* ---------------- 上传（含覆盖确认 + 自动备份） ---------------- */
async function adminLoadSubdirs() {
  // 从现有文件路径推导可选子目录（替代手动输入路径，消除输错风险）
  const dirs = new Set();
  ADMIN_FILES.forEach(f => {
    const parts = f.path.split('/');
    parts.pop();
    let cur = [];
    parts.forEach(p => { cur.push(p); dirs.add(cur.join('/')); });
  });
  const kind = $('#upKind').value;
  const keep = $('#upSubdir').value;
  const prefix = kind === 'pages' ? 'page_objects/app_ui/android/demoProject/pages/'
    : kind === 'elements' ? 'page_objects/app_ui/android/demoProject/elements/' : 'cases/';
  const options = ['', ...[...dirs].filter(d => d.startsWith(prefix))
    .map(d => d.slice(prefix.length)).sort()];
  $('#upSubdir').innerHTML = options.map(o =>
    '<option value="' + esc(o) + '">' + (o ? esc(o) : '（根目录）') + '</option>').join('');
  if (options.includes(keep)) $('#upSubdir').value = keep;
}

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
    // 同名覆盖确认（3.3）：展示原上传人与修改时间，确认后自动备份
    const m = d.meta || {};
    const yes = await confirmModal('⚠️ 覆盖同名文件',
      '该文件已存在，原上传人：' + (m.uploader || '框架') +
      '，修改时间：' + fmtDate(m.modify_time) +
      '。确认将覆盖旧文件，系统自动备份历史版本。', true);
    if (yes) { $('#btnUpload').textContent = '⏳ 上传中…'; await adminUpload(true); $('#btnUpload').textContent = '⬆ 上传'; }
    return;
  }
  toast(d.msg || (d.ok ? '上传成功' : '上传失败'), d.ok);
  if (d.ok) { fileInput.value = ''; adminLoadFiles(); }
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
    if (d.ok) { fileInput.value = ''; adminLoadFiles(); }
  } finally {
    btn.textContent = '📦 上传用例包'; btn.disabled = false;
  }
}

/* ---------------- 批量 / 重命名 / 新建文件夹 ---------------- */
async function adminBatchDelete() {
  const paths = adminSelected().filter(p => {
    const f = ADMIN_FILES.find(x => x.path === p);
    return f && !f.is_protected;
  });
  const protectedCount = adminSelected().length - paths.length;
  if (!paths.length) return toast('请先勾选要删除的文件（受保护文件不可删除）', false);
  const yes = await confirmModal('批量删除',
    '将删除选中的 ' + paths.length + ' 个文件，不可恢复。' +
    (protectedCount ? '另有 ' + protectedCount + ' 个框架公共文件将被跳过（仅管理员可操作）。' : ''), true);
  if (!yes) return;
  const d = await adminApi('/api/admin/batch_delete', {method: 'POST', body: JSON.stringify({paths: paths})});
  toast(d.msg || (d.ok ? '已执行' : '失败'), d.ok);
  adminLoadFiles();
}

function adminBatchDownload() {
  const paths = adminSelected();
  if (!paths.length) return toast('请先勾选要下载的文件', false);
  window.location = '/api/admin/download_batch?paths=' + encodeURIComponent(paths.join(','));
}

async function adminRename(path) {
  const f = ADMIN_FILES.find(x => x.path === path);
  const newName = prompt('重命名（保留 test_ 前缀 / .py 后缀）：', path.split('/').pop());
  if (!newName || newName === path.split('/').pop()) return;
  const d = await adminApi('/api/admin/rename', {method: 'POST', body: JSON.stringify({path: path, new_name: newName.trim()})});
  toast(d.msg || (d.ok ? '已重命名' : '失败'), d.ok);
  adminLoadFiles();
}

async function adminMkDir() {
  const kind = $('#upKind').value;
  const name = prompt('新文件夹名（位于 ' + (kind === 'cases' ? 'cases/' : kind) + ' 下，可含子层级 a/b）：');
  if (!name) return;
  const d = await adminApi('/api/admin/folder', {method: 'POST', body: JSON.stringify({kind: kind, subdir: name.trim()})});
  toast(d.msg || (d.ok ? '已创建' : '失败'), d.ok);
  adminLoadFiles();
}

/* ---------------- 初始化 ---------------- */
function adminInit() {
  renderSidebar('/admin');
  adminLoadFiles();
  $('#btnUpload').addEventListener('click', () => adminUpload(false));
  $('#btnUploadPkg').addEventListener('click', adminUploadPackage);
  $('#btnToken').addEventListener('click', () => {
    localStorage.setItem('adminToken', $('#inToken').value.trim());
    toast('口令已保存到本机浏览器');
    adminLoadFiles();
  });
  $('#typeFilter').addEventListener('change', adminRenderList);
  $('#upKind').addEventListener('change', () => { adminLoadSubdirs(); });
  $('#btnMkDir').addEventListener('click', adminMkDir);
  $('#btnBatchDownload').addEventListener('click', adminBatchDownload);
  $('#btnBatchDelete').addEventListener('click', adminBatchDelete);
  $('#ckAll').addEventListener('change', (e) => {
    document.querySelectorAll('#fileList .ck-file').forEach(c => {
      const f = ADMIN_FILES.find(x => x.path === c.dataset.path);
      if (f && f.is_protected) { c.checked = false; return; }  // 受保护文件不参与批量删除
      c.checked = e.target.checked;
    });
  });
  $('#fileList').addEventListener('click', (e) => {
    const del = e.target.closest('.admin-del');
    if (del) {
      const yes = confirmModal('删除文件', '将删除 ' + del.dataset.path + '，不可恢复。', true).then(yes => {
        if (yes) adminApi('/api/admin/file?path=' + encodeURIComponent(del.dataset.path), {method: 'DELETE'})
          .then(d => { toast(d.msg || (d.ok ? '已删除' : '失败'), d.ok); adminLoadFiles(); });
      });
      return;
    }
    const ren = e.target.closest('.admin-rename');
    if (ren) adminRename(ren.dataset.path);
  });
}

document.addEventListener('DOMContentLoaded', adminInit);
