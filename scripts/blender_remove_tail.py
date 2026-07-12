#!/usr/bin/env python3
"""
Blender Headless 脚本：从原始薄荷宿舍.pmx精确切除尾巴
用法: blender --background --python blender_remove_tail.py

策略:
1. 导入原始PMX
2. 识别所有尾巴相关骨骼 (Bn_m_tail_*)
3. 找到主网格中仅受尾巴骨骼影响的顶点 → 删除
4. 混合权重顶点（尾巴+身体）→ 移除尾巴权重并重新归一化
5. 删除尾巴骨骼链
6. 删除尾巴刚体和关节对象
7. 导出为新PMX
"""

import bpy
import sys
import os
import re

# ============================================================
# 配置
# ============================================================
INPUT_PMX = '/Users/admin/projects/mmd-agent-motion/models/薄荷宿舍/薄荷宿舍.pmx'
OUTPUT_PMX = '/Users/admin/projects/mmd-agent-motion/models/薄荷宿舍/薄荷宿舍_去尾巴v2.pmx'
LOG_PREFIX = '[TAIL_REMOVE]'

def log(msg):
    print(f'{LOG_PREFIX} {msg}', flush=True)

# ============================================================
# Step 0: 准备环境
# ============================================================
log('=== 开始尾巴切除流程 ===')

# 加载 mmd_tools
mmd_path = os.path.expanduser('~/Library/Application Support/Blender/5.1/extensions/add-ons')
if mmd_path not in sys.path:
    sys.path.insert(0, mmd_path)

import mmd_tools
mmd_tools.register()

# 清空场景
bpy.ops.wm.read_factory_settings(use_empty=True)

# ============================================================
# Step 1: 导入原始模型
# ============================================================
log(f'导入模型: {INPUT_PMX}')
bpy.ops.mmd_tools.import_model(
    filepath=INPUT_PMX,
    scale=1.0,
    types={'MESH', 'ARMATURE', 'MORPHS', 'PHYSICS', 'DISPLAY'}
)
log('导入完成')

# ============================================================
# Step 2: 找到关键对象
# ============================================================
# 找主网格对象（顶点数最多的那个）
mesh_objects = [o for o in bpy.data.objects if o.type == 'MESH']
main_mesh_obj = max(mesh_objects, key=lambda o: len(o.data.vertices))
log(f'主网格: {main_mesh_obj.name} ({len(main_mesh_obj.data.vertices)} 顶点, {len(main_mesh_obj.data.polygons)} 面)')

# 找骨架
armature_obj = [o for o in bpy.data.objects if o.type == 'ARMATURE'][0]
log(f'骨架: {armature_obj.name} ({len(armature_obj.data.bones)} 骨骼)')

# ============================================================
# Step 3: 识别尾巴骨骼
# ============================================================
TAIL_BONE_PATTERN = re.compile(r'Bn_m_tail', re.IGNORECASE)

tail_bone_names = set()
for bone in armature_obj.data.bones:
    if TAIL_BONE_PATTERN.search(bone.name):
        tail_bone_names.add(bone.name)

log(f'识别到 {len(tail_bone_names)} 个尾巴骨骼:')
for bn in sorted(tail_bone_names):
    log(f'  - {bn}')

# ============================================================
# Step 4: 识别尾巴顶点组
# ============================================================
tail_vg_names = set()
for vg in main_mesh_obj.vertex_groups:
    if TAIL_BONE_PATTERN.search(vg.name):
        tail_vg_names.add(vg.name)

log(f'识别到 {len(tail_vg_names)} 个尾巴顶点组')

# ============================================================
# Step 5: 分析每个顶点的权重，分类处理
# ============================================================
log('分析顶点权重分布...')

mesh = main_mesh_obj.data
total_verts = len(mesh.vertices)

# 建立顶点组索引 → 名称映射
vg_index_to_name = {}
for vg in main_mesh_obj.vertex_groups:
    vg_index_to_name[vg.index] = vg.name

# 分类顶点
pure_tail_verts = []     # 纯尾巴顶点（100% 权重在尾巴骨骼上）
mixed_tail_verts = []    # 混合权重顶点（部分在尾巴骨骼上）
total_tail_weight_per_vert = {}  # 每个顶点的尾巴权重总和

for vert in mesh.vertices:
    tail_weight_sum = 0.0
    has_tail = False
    has_non_tail = False
    
    for g in vert.groups:
        vg_name = vg_index_to_name.get(g.group, '')
        if vg_name in tail_vg_names:
            tail_weight_sum += g.weight
            has_tail = True
        else:
            if g.weight > 0.001:  # 忽略极小权重
                has_non_tail = True
    
    if has_tail:
        total_tail_weight_per_vert[vert.index] = tail_weight_sum
        if not has_non_tail or tail_weight_sum > 0.999:
            pure_tail_verts.append(vert.index)
        elif tail_weight_sum > 0.01:
            mixed_tail_verts.append(vert.index)

log(f'纯尾巴顶点（将删除）: {len(pure_tail_verts)} 个')
log(f'混合权重顶点（将清理尾巴权重）: {len(mixed_tail_verts)} 个')
log(f'不受影响的顶点: {total_verts - len(pure_tail_verts) - len(mixed_tail_verts)} 个')

# ============================================================
# Step 6: 删除纯尾巴顶点（Edit Mode）
# ============================================================
if pure_tail_verts:
    log(f'删除 {len(pure_tail_verts)} 个纯尾巴顶点...')
    
    # 切换到编辑模式
    bpy.context.view_layer.objects.active = main_mesh_obj
    bpy.ops.object.mode_set(mode='EDIT')
    
    # 取消全选
    bpy.ops.mesh.select_all(action='DESELECT')
    
    # 切回对象模式来设置顶点选择
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # 选择纯尾巴顶点
    for idx in pure_tail_verts:
        mesh.vertices[idx].select = True
    
    # 切到编辑模式删除
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.delete(type='VERT')
    
    # 回到对象模式
    bpy.ops.object.mode_set(mode='OBJECT')
    
    log(f'删除完成，剩余顶点: {len(mesh.vertices)}')

# ============================================================
# Step 7: 清理混合权重顶点中的尾巴权重
# ============================================================
# 注意：删除顶点后，顶点索引会变，但 vertex_groups 的 group index 不变
# 我们需要重新分析剩余顶点的混合权重

log('重新分析并清理混合权重顶点...')

# 重建顶点组索引映射（删除顶点后需要重建）
vg_index_to_name_fresh = {}
for vg in main_mesh_obj.vertex_groups:
    vg_index_to_name_fresh[vg.index] = vg.name

mesh = main_mesh_obj.data  # 刷新mesh引用
cleaned_count = 0

for vert in mesh.vertices:
    has_tail_group = False
    groups_to_remove = []
    remaining_weight = 0.0
    
    for g in vert.groups:
        vg_name = vg_index_to_name_fresh.get(g.group, '')
        if vg_name in tail_vg_names:
            if g.weight > 0.001:
                has_tail_group = True
                groups_to_remove.append((g.group, g.weight))
        else:
            remaining_weight += g.weight
    
    if has_tail_group and remaining_weight > 0.001:
        # 有尾巴权重且有其他权重 → 移除尾巴权重并归一化剩余权重
        for group_idx, _ in groups_to_remove:
            main_mesh_obj.vertex_groups[group_idx].remove([vert.index])
        
        # 重新归一化剩余权重
        if remaining_weight > 0.001:
            for g in vert.groups:
                vg_name = vg_index_to_name_fresh.get(g.group, '')
                if vg_name not in tail_vg_names and g.weight > 0.001:
                    new_weight = g.weight / remaining_weight
                    main_mesh_obj.vertex_groups[g.group].add([vert.index], new_weight, 'REPLACE')
        
        cleaned_count += 1
    elif has_tail_group:
        # 仅有尾巴权重（但我们没删掉的）→ 也移除
        for group_idx, _ in groups_to_remove:
            main_mesh_obj.vertex_groups[group_idx].remove([vert.index])
        cleaned_count += 1

log(f'清理了 {cleaned_count} 个混合权重顶点')

# ============================================================
# Step 8: 删除尾巴顶点组
# ============================================================
log('删除尾巴顶点组...')
# 从后往前删（避免索引偏移）
tail_vg_indices = sorted(
    [vg.index for vg in main_mesh_obj.vertex_groups if vg.name in tail_vg_names],
    reverse=True
)
for idx in tail_vg_indices:
    main_mesh_obj.vertex_groups.remove(main_mesh_obj.vertex_groups[idx])
log(f'已删除 {len(tail_vg_indices)} 个尾巴顶点组')

# ============================================================
# Step 9: 删除尾巴骨骼
# ============================================================
log('删除尾巴骨骼...')
bpy.context.view_layer.objects.active = armature_obj
bpy.ops.object.mode_set(mode='EDIT')

tail_bones_deleted = 0
for bone_name in sorted(tail_bone_names):
    if bone_name in armature_obj.data.edit_bones:
        armature_obj.data.edit_bones.remove(armature_obj.data.edit_bones[bone_name])
        tail_bones_deleted += 1

bpy.ops.object.mode_set(mode='OBJECT')
log(f'已删除 {tail_bones_deleted} 个尾巴骨骼')

# ============================================================
# Step 10: 删除尾巴刚体和关节对象
# ============================================================
log('删除尾巴刚体和关节对象...')

tail_objects_deleted = 0
objs_to_delete = []
for obj in bpy.data.objects:
    obj_name_lower = obj.name.lower()
    if 'tail' in obj_name_lower or 'm_tail' in obj_name_lower:
        objs_to_delete.append(obj)

for obj in objs_to_delete:
    bpy.data.objects.remove(obj, do_unlink=True)
    tail_objects_deleted += 1

log(f'已删除 {tail_objects_deleted} 个尾巴相关对象（刚体/关节/其他）')

# ============================================================
# Step 11: 验证
# ============================================================
log('=== 验证 ===')

# 检查是否还有尾巴残留
remaining_tail_bones = [b.name for b in armature_obj.data.bones if 'tail' in b.name.lower()]
remaining_tail_vgs = [vg.name for vg in main_mesh_obj.vertex_groups if 'tail' in vg.name.lower()]
remaining_tail_objs = [o.name for o in bpy.data.objects if 'tail' in o.name.lower()]

log(f'残留尾巴骨骼: {len(remaining_tail_bones)} ({remaining_tail_bones})')
log(f'残留尾巴顶点组: {len(remaining_tail_vgs)} ({remaining_tail_vgs})')
log(f'残留尾巴对象: {len(remaining_tail_objs)} ({remaining_tail_objs})')
log(f'最终顶点数: {len(mesh.vertices)}')
log(f'最终面数: {len(mesh.polygons)}')

# ============================================================
# Step 12: 导出新PMX
# ============================================================
log(f'导出到: {OUTPUT_PMX}')
# 导出需要选中MMD根对象（empty类型的薄荷宿舍）
root_obj = None
for obj in bpy.data.objects:
    if obj.type == 'EMPTY' and '薄荷宿舍' in obj.name and '_arm' not in obj.name and '_mesh' not in obj.name:
        root_obj = obj
        break

if root_obj is None:
    # 备选：找第一个empty对象
    empties = [o for o in bpy.data.objects if o.type == 'EMPTY']
    if empties:
        root_obj = empties[0]

if root_obj:
    log(f'导出根对象: {root_obj.name}')
    bpy.ops.object.select_all(action='DESELECT')
    root_obj.select_set(True)
    bpy.context.view_layer.objects.active = root_obj
    bpy.ops.mmd_tools.export_pmx(filepath=OUTPUT_PMX, scale=1.0)
    log('导出完成!')
else:
    log('错误: 未找到MMD根对象！尝试直接导出...')
    bpy.ops.mmd_tools.export_pmx(filepath=OUTPUT_PMX, scale=1.0)
    log('导出完成!')

# ============================================================
# Step 13: 文件大小对比
# ============================================================
orig_size = os.path.getsize(INPUT_PMX)
new_size = os.path.getsize(OUTPUT_PMX)
log(f'原文件大小: {orig_size:,} bytes')
log(f'新文件大小: {new_size:,} bytes')
log(f'大小差异: {orig_size - new_size:,} bytes ({(1 - new_size/orig_size)*100:.1f}%)')

log('=== 尾巴切除流程全部完成 ===')
