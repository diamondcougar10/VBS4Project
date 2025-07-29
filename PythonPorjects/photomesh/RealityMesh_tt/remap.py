#Tested in Blender 4.2.3 & 4.3.0

import bpy
import bmesh
import time	 # Import the time module
import math

import sys
import os

def export_lods_to_glb(lod_objects, filepath):
	# Deselect all objects
	bpy.ops.object.select_all(action='DESELECT')

	# Create dummy empty nodes for each LOD and parent the LOD objects
	for i, lod_obj in enumerate(lod_objects):
		bpy.ops.object.empty_add(type='PLAIN_AXES')
		lod_empty = bpy.context.object
		lod_empty.name = f"LOD_{i:02d}"
		print(f"Dummy empty node created: {lod_empty.name}")

		lod_obj.select_set(True)
		bpy.context.view_layer.objects.active = lod_empty
		bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)
		print(f"LOD object '{lod_obj.name}' parented to dummy empty node '{lod_empty.name}'")

	# Deselect all objects again to ensure clean selection
	bpy.ops.object.select_all(action='DESELECT')

	# Select the dummy empty nodes and their children to export
	for i in range(len(lod_objects)):
		lod_empty = bpy.data.objects[f"LOD_{i:02d}"]
		lod_empty.select_set(True)
		for child in lod_empty.children:
			child.select_set(True)
	bpy.context.view_layer.objects.active = bpy.data.objects["LOD_00"]

	# Export the dummy empty nodes (and their children) to GLB
	bpy.ops.export_scene.gltf(filepath=filepath, export_format='GLB', use_selection=True)
	print(f"Exported LODs to {filepath}")

def generate_lods(obj, lod_face_threshold, lod_num_threshold):
	"""
	Generate LODs for a given object using the Decimate modifier.
	Calculate the number of LODs based on input thresholds
	"""
	lod_objects = []
	lod_objects.append(obj)
	for i in range(math.floor(lod_num_threshold)):
		factor = pow(0.5, i + 1)
		if len(obj.data.polygons) * factor < lod_face_threshold:
			continue
		# Duplicate the object
		lod_obj = obj.copy()
		lod_obj.data = obj.data.copy()
		lod_obj.name = f"{obj.name}_LOD{i+1:02d}"
		bpy.context.collection.objects.link(lod_obj)
		
		# Apply a Decimate modifier
		decimate_mod = lod_obj.modifiers.new(name="Decimate", type='DECIMATE')
		decimate_mod.ratio = factor

		# Optionally apply the modifier to freeze the geometry
		bpy.context.view_layer.objects.active = lod_obj
		bpy.ops.object.modifier_apply(modifier=decimate_mod.name)

		lod_objects.append(lod_obj)
		print(f"Generated LOD {i+1} with decimation factor {factor}, {len(lod_obj.data.polygons)} faces")

	return lod_objects

# Automatically find the first mesh in the scene
def find_first_mesh():
	for obj in bpy.context.scene.objects:
		if obj.type == 'MESH':
			return obj
	raise ValueError("No mesh object found in the scene.")

def determine_texture_size_by_face_count(obj):
	# Count the number of faces
	face_count = len(obj.data.polygons)
	print(f"Face count: {face_count}")
	
	# Determine texture size based on face count
	if face_count < 100:	   # Smallererer mesh
		return 256, 256
	elif face_count < 500:		 # Smallerer mesh
		return 512, 512
	elif face_count < 1000:		  # Smaller mesh
		return 1024, 1024
	elif face_count < 2000:		  # Small mesh
		return 2048, 2048
	elif face_count < 276000:	 # Medium mesh
		return 4096, 4096
	else:						# Large mesh
		return 8192, 8192

def run_operations():
	# Import fbx model
	bpy.ops.object.select_all(action='SELECT')
	bpy.ops.object.delete()
	bpy.ops.import_scene.fbx(filepath=inFBX)
	print(f"Imported FBX file: {inFBX}")

	bpy.ops.object.select_all(action='SELECT')
	print("All objects selected after import.")

	# Find the camera and light objects
	camera = bpy.data.objects.get('Camera')
	light = bpy.data.objects.get('Light')

	# Check if the camera exists
	if camera:
		# Remove the camera object from the scene
		bpy.data.objects.remove(camera, do_unlink=True)
		print("Camera deleted from the scene.")
	else:
		print("No camera found in the scene.")

	# Check if the light exists
	if light:
		# Remove the light object from the scene
		bpy.data.objects.remove(light, do_unlink=True)
		print("Light deleted from the scene.")
	else:
		print("No light found in the scene.")

def duplicate_mesh(obj, suffix):
	""" Duplicate the given mesh object and return the new duplicate with a unique name. """
	# Deselect all objects
	bpy.ops.object.select_all(action='DESELECT')
	
	# Select the specific object to duplicate
	obj.select_set(True)
	bpy.context.view_layer.objects.active = obj
	
	# Duplicate the selected object
	bpy.ops.object.duplicate()
	
	# Get the duplicated object (the last active object after duplication)
	duplicated_obj = bpy.context.view_layer.objects.active
	duplicated_obj.name = f"{obj.name}_{suffix}"
	print(f"Duplicated object: {duplicated_obj.name}")
	
	return duplicated_obj

def apply_smart_uv_unwrap(obj, uv_map_name):
	""" Applies Smart UV Project to the provided object and applies additional UV steps. """
	# Deselect all objects to ensure a clean selection context
	bpy.ops.object.select_all(action='DESELECT')
	
	# Select and activate the object
	obj.select_set(True)
	bpy.context.view_layer.objects.active = obj

	# Set the duplicated object as active and enter Edit Mode
	bpy.ops.object.mode_set(mode='EDIT')
	
	# Ensure all faces are selected
	bpy.ops.mesh.select_all(action='SELECT')
	
	# Perform Smart UV Project with specified parameters
	bpy.ops.uv.smart_project(angle_limit=1.22173, island_margin=0.003, area_weight=1.0)
	print(f"Smart UV Project applied to {obj.name} with angle limit of 70 degrees and island margin of 0.02.")

	# Rename the UV map to a unique name
	uv_map = obj.data.uv_layers.active
	uv_map.name = uv_map_name
	print(f"UV map renamed to {uv_map_name} for {obj.name}.")

	# Additional UV steps:
	
	# Ensure all UVs are selected before applying Average Island Scale
	bpy.ops.uv.select_all(action='SELECT')
	print("All UVs selected.")

	# Remove Doubles
	bpy.ops.mesh.remove_doubles()
	print("Remove Doubles applied.")

	# Set Sharpness by Angle from argv[2]
	bpy.ops.mesh.set_sharpness_by_angle(angle=sharpAngle)
	print("Set Sharpness by Angle applied.")
	
	# Apply Average Island Scale
	bpy.ops.uv.average_islands_scale()
	print("Average Island Scale applied.")

	# Apply Minimize Stretch
	bpy.ops.uv.minimize_stretch(blend=0.25, iterations=60)
	print("Minimize Stretch applied with Blend at 0.25 and Iterations at 60.")

	# Pack UV Islands with a margin of 0.003
	bpy.ops.uv.pack_islands(udim_source='ORIGINAL_AABB', margin=0.003)
	print("UV Islands packed with margin 0.003.")

	# Return to Object Mode after UV processing
	bpy.ops.object.mode_set(mode='OBJECT')
	print(f"UV processing completed and returned to Object Mode for {obj.name}.")

def delete_materials(obj):
	""" Deletes all materials attached to the specified object. """
	if obj.data.materials:
		obj.data.materials.clear()
		print(f"All materials deleted from {obj.name}.")
	else:
		print(f"No materials found on {obj.name} to delete.")

def add_and_configure_material(obj):
	""" Adds a uniquely named material to the object, configures the BSDF settings. """
	# Create a new material with a unique name
	material_name = f"{obj.name}_Material"
	material = bpy.data.materials.new(name=material_name)
	material.use_nodes = True
	obj.data.materials.append(material)
	print(f"New material '{material_name}' created and assigned to {obj.name}.")

	# Get the Principled BSDF node and set properties
	bsdf_node = material.node_tree.nodes.get("Principled BSDF")
	if bsdf_node:
		bsdf_node.inputs['Roughness'].default_value = 1.0
		print("Set Roughness to 1 on the Principled BSDF.")

		bsdf_node.inputs['IOR'].default_value = 1.0
		print("Set IOR to 1 on the Principled BSDF for minimum refraction effect.")

		# Corrected this line as per your request
		bsdf_node.inputs['Specular IOR Level'].default_value = 0.0
		print("Set Specular IOR Level to 0 on the Principled BSDF for no specular reflection.")
	
	# Set texture dimensions based on face count
	texture_width, texture_height = determine_texture_size_by_face_count(obj)
	print(f"Texture size determined: {texture_width}x{texture_height}")

	# Initialize the image variable if it doesn't exist
	image = None  # Make sure the image variable is initialized before use.

	# Check if an image is provided, otherwise create a new image
	if image is None:
		# Create a new image based on the calculated texture size
		image = bpy.data.images.new(name=f"{obj.name}_Texture", width=texture_width, height=texture_height)
		print(f"Created new image with size {texture_width}x{texture_height}.")
	else:
		# Ensure the image exists
		if not image.is_loaded:
			image.reload()	# Reload the image if it's not loaded
			print(f"Reloaded the existing image '{image.name}'.")

	# Get the existing material of the new object (if it has one)
	bsdf_node = material.node_tree.nodes.get("Principled BSDF")
	
	if bsdf_node:
		bsdf_node.inputs['Roughness'].default_value = 1.0
		print("Set Roughness to 1 on the Principled BSDF.")
		bsdf_node.inputs['IOR'].default_value = 1.0
		print("Set IOR to 1 on the Principled BSDF for minimum refraction effect.")
		bsdf_node.inputs['Specular IOR Level'].default_value = 0.0
		print("Set Specular IOR Level to 0 on the Principled BSDF for no specular reflection.")
	
	# Enable nodes for the material if not already enabled
	if not material.use_nodes:
		material.use_nodes = True
		print("Enabled nodes for the material.")
	
	# Get the shader node tree
	node_tree = material.node_tree
	
	# Create the Image Texture Node
	texture_node = node_tree.nodes.new("ShaderNodeTexImage")
	texture_node.image = image
	print(f"Image texture node created and assigned the image: {image.name}.")
	
	# Get the Principled BSDF shader node
	if bsdf_node:
		# Connect the image texture to the Base Color of the Principled BSDF
		node_tree.links.new(texture_node.outputs['Color'], bsdf_node.inputs['Base Color'])
		print("Image texture connected to the Base Color of the Principled BSDF.")

def apply_uv_scaling_and_centering(obj):
	""" Apply the UV scaling and centering operation on the given object """
	try:
		if obj and obj.type == 'MESH':
			# Ensure the object is in Object Mode
			bpy.ops.object.mode_set(mode='OBJECT')

			# Deselect all objects to ensure a clean selection context
			bpy.ops.object.select_all(action='DESELECT')

			# Select and activate the object to ensure operations apply to it
			obj.select_set(True)
			bpy.context.view_layer.objects.active = obj
			print(f"Object '{obj.name}' set to active and selected for UV scaling and centering.")

			# Ensure the active material has an image texture node
			material = obj.active_material
			if not material or not material.use_nodes:
				print("No active material with nodes found.")
				return

			# Find the image texture node in the material's node tree
			image_texture_node = None
			for node in material.node_tree.nodes:
				if node.type == 'TEX_IMAGE':
					image_texture_node = node
					break

			if not image_texture_node or not image_texture_node.image:
				print("No image texture found in the material.")
				return

			# Get image dimensions
			image = image_texture_node.image
			texture_width = image.size[0]
			texture_height = image.size[1]
			aspect_ratio = texture_width / texture_height
			print(f"Image dimensions: {texture_width}x{texture_height}, Aspect ratio: {aspect_ratio}")

			# Ensure all UVs are selected before scaling
			bpy.ops.object.mode_set(mode='OBJECT')
			uv_layer = obj.data.uv_layers.active.data

			if not uv_layer:
				print("No active UV layer found.")
				return

			# Print the name of the UV map being worked on
			uv_map_name = obj.data.uv_layers.active.name
			print(f"Working on UV map: {uv_map_name}")

			# Find UV bounds
			min_u = min((uv.uv[0] for uv in uv_layer), default=None)
			max_u = max((uv.uv[0] for uv in uv_layer), default=None)
			min_v = min((uv.uv[1] for uv in uv_layer), default=None)
			max_v = max((uv.uv[1] for uv in uv_layer), default=None)

			if min_u is None or max_u is None or min_v is None or max_v is None:
				print("UV layer is empty.")
				return

			uv_width = max_u - min_u
			uv_height = max_v - min_v

			print(f"UV bounds before scaling: min_u={min_u}, max_u={max_u}, min_v={min_v}, max_v={max_v}")

			# Center the UV map
			for uv_data in uv_layer:
				uv_data.uv[0] -= min_u + uv_width / 2
				uv_data.uv[1] -= min_v + uv_height / 2

			# Determine scaling factors
			scale_factor = 0.97	 # Scale down to 90% to ensure UVs are smaller than 1
			if aspect_ratio > 1:
				scale_u = scale_factor / uv_width
				scale_v = (scale_factor / uv_height) * aspect_ratio
			else:
				scale_u = (scale_factor / uv_width) / aspect_ratio
				scale_v = scale_factor / uv_height

			print(f"Scaling factors: scale_u={scale_u}, scale_v={scale_v}")

			# Apply scaling
			for uv_data in uv_layer:
				uv_data.uv[0] *= scale_u
				uv_data.uv[1] *= scale_v

			# Center UVs within the 0-1 grid
			for uv_data in uv_layer:
				uv_data.uv[0] += 0.5
				uv_data.uv[1] += 0.5

			print(f"UV map scaled and centered for {obj.name}.")

			# Set smooth shading for output object
			bpy.ops.object.shade_smooth()
			print("Smooth Shading set.")

			bpy.ops.object.mode_set(mode='EDIT')  # Return to edit mode if needed

			# Print UV bounds after scaling
			min_u = min((uv.uv[0] for uv in uv_layer), default=None)
			max_u = max((uv.uv[0] for uv in uv_layer), default=None)
			min_v = min((uv.uv[1] for uv in uv_layer), default=None)
			max_v = max((uv.uv[1] for uv in uv_layer), default=None)

			if min_u is None or max_u is None or min_v is None or max_v is None:
				print("UV layer is empty after scaling.")
				return

			print(f"UV bounds after scaling: min_u={min_u}, max_u={max_u}, min_v={min_v}, max_v={max_v}")
	except Exception as e:
		print(f"Error in apply_uv_scaling_and_centering: {e}")

def configure_principled_bsdf(obj):
	# Set Metallic to 0 on the Principled BSDF on original object
	for original_material in obj.data.materials:
		if original_material.use_nodes:
			bsdf_node = original_material.node_tree.nodes.get("Principled BSDF")
			if bsdf_node:
				bsdf_node.inputs['Metallic'].default_value = 0.0
				print("Set Metallic to 0 on the Principled BSDF.")

				bsdf_node.inputs['Roughness'].default_value = 1.0
				print("Set Roughness to 1 on the Principled BSDF.")

				# Set IOR to the lowest valid value of 1.0 for minimal refractive effect
				bsdf_node.inputs['IOR'].default_value = 1.0
				print("Set IOR to 1 on the Principled BSDF for minimum refraction effect.")

				# Set Specular to 0 to reduce reflectivity
				bsdf_node.inputs['Specular IOR Level'].default_value = 0.0
				print("Set Specular to 0 on the Principled BSDF for no specular reflection.")

def cut_mesh_in_half(export_path="", face_threshold=500000, lod_face_threshold=500, lod_num_threshold=5):
	# Check for selected objects in the context
	selected_objects = bpy.context.selected_objects

	# If no objects are selected, find the first mesh object in the scene and select it
	if not selected_objects:
		for obj in bpy.data.objects:
			if obj.type == 'MESH':
				obj.select_set(True)
				bpy.context.view_layer.objects.active = obj
				print(f"Selected mesh object: {obj.name}")
				selected_objects = [obj]  # Update to include the selected object
				break
			else:
				print(f"Skipped object: {obj.name}")
		else:
			print("No mesh objects found in the scene.")
			return	# Exit if no mesh is found
	else:
		# Use the first selected object
		original_object = selected_objects[0]
		bpy.context.view_layer.objects.active = original_object
		if original_object.type != 'MESH':
			print("The first selected object is not a mesh.")
			return
		else:
			print(f"Selected mesh object: {original_object.name}")

	# Define the original mesh object for cutting
	original_object = bpy.context.view_layer.objects.active
	
	# Configure the Principled BSDF shader of the original object
	configure_principled_bsdf(original_object)

	# Determine if the mesh qualifies as "large" based on face count
	face_count = len(original_object.data.polygons)
	print(f"Face count: {face_count}")
	
	# Print memory resources consumed
	print(f"Blender memory usage: {bpy.context.preferences.system.memory_cache_limit} MB")

	if face_count < face_threshold:
		print(f"Mesh '{original_object.name}' does not exceed the face threshold of {face_threshold}.")
		# Duplicate and apply Smart UV Project to the duplicate if the mesh is small or medium
		duplicated_object = duplicate_mesh(original_object, "dup")
		apply_smart_uv_unwrap(duplicated_object, f"{duplicated_object.name}_UVMap")
		delete_materials(duplicated_object)
		add_and_configure_material(duplicated_object)
		apply_uv_scaling_and_centering(duplicated_object)  # Apply UV scaling and centering
		prepare_for_baking(original_object, duplicated_half1=duplicated_object, export_path=export_path, lod_face_threshold=lod_face_threshold, lod_num_threshold=lod_num_threshold)
		return	# Exit if the mesh does not exceed the face threshold
	else:
		print(f"Mesh '{original_object.name}' exceeds the face threshold of {face_threshold}. Splitting the mesh.")

	# Create a new bmesh to work with
	bm = bmesh.new()
	bm.from_mesh(original_object.data)

	# Calculate the center of the bounding box
	min_x, max_x = min([v.co.x for v in bm.verts]), max([v.co.x for v in bm.verts])
	min_y, max_y = min([v.co.y for v in bm.verts]), max([v.co.y for v in bm.verts])
	min_z, max_z = min([v.co.z for v in bm.verts]), max([v.co.z for v in bm.verts])

	# Center coordinates based on bounding box
	center_x = (min_x + max_x) / 2
	center_y = (min_y + max_y) / 2
	center_z = (min_z + max_z) / 2
	bm.free()

	# Duplicate the original object so we have two halves after cutting
	bpy.ops.object.select_all(action='DESELECT')
	original_object.select_set(True)
	bpy.context.view_layer.objects.active = original_object
	bpy.ops.object.duplicate()

	# Get the two objects (the duplicate is now the active object)
	obj_half1 = bpy.context.view_layer.objects.active  # First half (active after duplicate)
	obj_half2 = original_object	 # Original object (second half)
	print(f"Duplicated objects: {obj_half1.name}, {obj_half2.name}")

	# Add a plane to be used as the cut plane, aligned to the bounding box center
	bpy.ops.mesh.primitive_plane_add(size=150, location=(center_x, center_y, center_z))
	plane = bpy.context.object
	print("Cut plane added.")

	# Align the plane with the Y axis at the object's center
	plane.rotation_euler[0] = 1.5708  # Rotate the plane 90 degrees to align with the X-Y Plane

	# Apply transformations (rotation, location, etc.) to the plane
	bpy.context.view_layer.update()

	# Perform the bisect on obj_half1
	bpy.context.view_layer.objects.active = obj_half1
	bpy.ops.object.mode_set(mode='EDIT')
	bpy.ops.mesh.select_all(action='SELECT')
	bpy.ops.mesh.bisect(plane_co=plane.location, plane_no=(1, 0, 0), clear_inner=True)	# Y-axis bisect
	print(f"Bisect performed on {obj_half1.name}, inner side cleared.")

	# Switch back to Object Mode for obj_half1 after cutting
	bpy.ops.object.mode_set(mode='OBJECT')

	# Now repeat for obj_half2, clearing the outer side
	bpy.context.view_layer.objects.active = obj_half2
	bpy.ops.object.mode_set(mode='EDIT')
	bpy.ops.mesh.select_all(action='SELECT')
	bpy.ops.mesh.bisect(plane_co=plane.location, plane_no=(1, 0, 0), clear_outer=True)	# Y-axis bisect
	print(f"Bisect performed on {obj_half2.name}, outer side cleared.")

	# Switch back to Object Mode for obj_half2
	bpy.ops.object.mode_set(mode='OBJECT')

	# Delete the plane object used for the cut
	bpy.data.objects.remove(plane, do_unlink=True)

	# Update the scene
	bpy.context.view_layer.update()

	# Duplicate each of the halves exactly once
	duplicated_half1 = duplicate_mesh(obj_half1, "half1_dup")
	duplicated_half2 = duplicate_mesh(obj_half2, "half2_dup")

	# Apply Smart UV Unwrap, delete materials, add new material, and configure BSDF for each half
	apply_smart_uv_unwrap(duplicated_half1, f"{duplicated_half1.name}_UVMap")
	delete_materials(duplicated_half1)
	add_and_configure_material(duplicated_half1)

	apply_smart_uv_unwrap(duplicated_half2, f"{duplicated_half2.name}_UVMap")
	delete_materials(duplicated_half2)
	add_and_configure_material(duplicated_half2)

	# Apply UV scaling and centering at the end
	apply_uv_scaling_and_centering(duplicated_half1)
	apply_uv_scaling_and_centering(duplicated_half2)

	# Return both duplicated halves
	print(f"Mesh '{original_object.name}' has been cut into two parts along the Y-axis.")
	print(f"Duplicated meshes: {duplicated_half1.name}, {duplicated_half2.name}")

	# Add the function call here for duplicated halves
	prepare_for_baking(obj_half1, obj_half2, duplicated_half1, duplicated_half2, export_path=export_path, lod_face_threshold=lod_face_threshold, lod_num_threshold=lod_num_threshold)

def join_meshes_with_materials(obj1, obj2):
	print(f"Joining meshes: {obj1.name} and {obj2.name}")

	# Deselect all objects
	bpy.ops.object.select_all(action='DESELECT')
	print("All objects deselected.")

	# Select both objects
	obj1.select_set(True)
	obj2.select_set(True)
	bpy.context.view_layer.objects.active = obj1
	print(f"Selected objects: {obj1.name} and {obj2.name}")

	# Rename UV maps to the same name before joining
	uv_map_name = "UVMap_0"
	if obj1.data.uv_layers.active:
		obj1.data.uv_layers.active.name = uv_map_name
		print(f"Renamed UV map of {obj1.name} to {uv_map_name}")
	if obj2.data.uv_layers.active:
		obj2.data.uv_layers.active.name = uv_map_name
		print(f"Renamed UV map of {obj2.name} to {uv_map_name}")

	# Join the objects
	bpy.ops.object.join()
	print("Objects joined.")

	# Deselect all objects again to ensure clean selection
	bpy.ops.object.select_all(action='DESELECT')

	# Get the joined object (the active object after the join operation)
	joined_obj = bpy.context.view_layer.objects.active

	# Select the joined object
	joined_obj.select_set(True)
	bpy.context.view_layer.objects.active = joined_obj
	print(f"Joined object reselected: {joined_obj.name}")

	print(f"UV maps in joined object: {[uv.name for uv in joined_obj.data.uv_layers]}")
	return joined_obj

def prepare_for_baking(original_half1, original_half2=None, duplicated_half1=None, duplicated_half2=None, export_path="", lod_face_threshold=500, lod_num_threshold=5):
	""" Prepare for baking by setting the render engine to Cycles, configuring bake settings, and exporting to GLB """
	# Switch to Cycles render engine
	bpy.context.scene.render.engine = 'CYCLES'
	print("Switched to Cycles render engine.")

	# Set render samples to 1
	bpy.context.scene.cycles.samples = 1
	print("Set render samples to 1.")

	# Configure bake settings
	bpy.context.scene.cycles.bake_type = 'DIFFUSE'
	bpy.context.scene.render.bake.use_selected_to_active = True
	bpy.context.scene.render.bake.use_pass_direct = False
	bpy.context.scene.render.bake.use_pass_indirect = False
	bpy.context.scene.render.bake.cage_extrusion = 0.2
	bpy.context.scene.render.bake.max_ray_distance = 0.3
	print("Bake settings configured.")

	def bake_texture(duplicated_obj, original_obj):
		# Ensure the context is correct
		bpy.context.view_layer.objects.active = duplicated_obj
		print(f"Context set to duplicated object: {bpy.context.view_layer.objects.active.name}")

		# Ensure the mesh is not in edit mode
		bpy.ops.object.mode_set(mode='OBJECT')
		print(f"Set mode to OBJECT for {duplicated_obj.name}")

		# Deselect all objects
		bpy.ops.object.select_all(action='DESELECT')
		print("All objects deselected.")

		# Select the duplicated mesh first to set it as the active target
		duplicated_obj.select_set(True)
		bpy.context.view_layer.objects.active = duplicated_obj
		print(f"Duplicated object '{duplicated_obj.name}' selected as active target.")

		# Shift-select the original mesh as the source
		original_obj.select_set(True)
		print(f"Original object '{original_obj.name}' selected as source.")

		# Bake the texture
		bpy.ops.object.bake(type='DIFFUSE', use_selected_to_active=True)
		print("Baking completed.")

	def export_to_glb(obj, filepath):
		# Deselect all objects
		bpy.ops.object.select_all(action='DESELECT')

		# Create a dummy empty node
		bpy.ops.object.empty_add(type='PLAIN_AXES')
		empty = bpy.context.object
		empty.name = "LOD_0"
		print(f"Dummy empty node created: {empty.name}")

		# Parent the object to the dummy empty node
		obj.select_set(True)
		bpy.context.view_layer.objects.active = empty
		bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)
		print(f"Object '{obj.name}' parented to dummy empty node '{empty.name}'")

		# Deselect all objects again to ensure clean selection
		bpy.ops.object.select_all(action='DESELECT')

		# Select the dummy empty node and its children to export
		empty.select_set(True)
		for child in empty.children:
			child.select_set(True)
		bpy.context.view_layer.objects.active = empty

		# Export the dummy empty node (and its children) to GLB
		bpy.ops.export_scene.gltf(filepath=filepath, export_format='GLB', use_selection=True)
		print(f"Exported {empty.name} and its children to {filepath}")

	# Bake each duplicated half or single mesh
	if duplicated_half1 and duplicated_half2:
		bake_texture(duplicated_half1, original_half1)
		bake_texture(duplicated_half2, original_half2)
		# Join the meshes and export
		joined_obj = join_meshes_with_materials(duplicated_half1, duplicated_half2)
		tex_name = os.path.splitext(os.path.basename(outFBX))[0]
		iter = 0
		for mat in joined_obj.data.materials: 
			if mat.use_nodes: 
				for node in mat.node_tree.nodes: 
					if node.type == 'TEX_IMAGE' and node.image: 
						iter += 1
						node.image.name = f"{tex_name}_{iter}"
						print(f"Renamed texture to: {node.image.name}") 
		export_to_glb(joined_obj, f"{export_path}")
		# Generate LODs
		lod_objects = generate_lods(joined_obj, lod_face_threshold, lod_num_threshold)

		# Export the LODs to a single GLB file
		export_lods_to_glb(lod_objects, f"{export_path}")
	else:
		bake_texture(duplicated_half1, original_half1)
		# Export the single duplicated mesh
		tex_name = os.path.splitext(os.path.basename(outFBX))[0]
		iter = 0
		for mat in duplicated_half1.data.materials: 
			if mat.use_nodes: 
				for node in mat.node_tree.nodes: 
					if node.type == 'TEX_IMAGE' and node.image: 
						iter += 1
						node.image.name = f"{tex_name}_{iter}"
						print(f"Renamed texture to: {node.image.name}") 
		# Generate LODs
		lod_objects = generate_lods(duplicated_half1, lod_face_threshold, lod_num_threshold)

		# Export the LODs to a single GLB file
		export_lods_to_glb(lod_objects, f"{export_path}")


argv = sys.argv
try:
	argv = argv[argv.index("--") + 1:]
except ValueError:
	argv = ["D:\\bdc\\tests\\OneClick_OneTile\\output_models\\convex155.fbx", "D:\\bdc\\tests\\OneClick_OneTile\\output_models_out\\convex155.glb", 0.523598775, 500,5]
inFBX = argv[0]
outFBX = argv[1]
sharpAngle = float(argv[2])
faceThresh = float(argv[3])
lodThresh = float(argv[4])

# Run deletion of camera and light first
run_operations()

# Run the cut and apply further operations on each half
cut_mesh_in_half(export_path=outFBX, face_threshold=500000, lod_face_threshold=faceThresh, lod_num_threshold=lodThresh)