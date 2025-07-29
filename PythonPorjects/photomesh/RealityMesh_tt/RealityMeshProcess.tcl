#This script should be started by a bat script that the user will run and will prompt them for
#inputs. The batch script should make input variables available to this .tcl file
#This TCL needs to be executed from the project folder

#Pull in paramaters from command file
global name
global blender_threads
global blender_path
global override_Installation_VBS4
global override_Installation_VBS4_bool
global override_Path_VBS4
global vbs4_version
global override_Installation_DevSuite
global override_Path_DevSuite
global offset_x
global offset_y
global offset_z
global offset_coordsys
global offset_hdatum
global offset_vdatum
global orthocam_Resolution
global orthocam_Render_Lowest
global tin_to_dem_Resolution
global sel_Area_Size
global out_in_name
global out_in_name_with_drive
global collision
global visualLODs
global project_vdatum
global offset_models
global csf_options
global faceThresh
global lodThresh
global tileSize
global srfResolution

set suffix _log.txt
set logName $name$suffix
puts $logName

set suffixttp .ttp
set ttp $name$suffixttp
puts $ttp

#Create log file
tsdlogfile $logName

#Load the project
tsdload $ttp

#Define nodes
set applylibraryscript "Apply Model Library Script"
set apply_feature_and_library_script "Apply Feature and Model Library Script 2"
set place_models "Place Models"
set export_las "Export LAS"
set offset "Offset Features 2"
set offset_2 "Offset Features Models"
set csf "PDAL Translate CSF"
set import_las "Import LAS"
set clip_tsg "Clip TSG by Polygons"
set blender "Blender Script Runner"
set exporter "Export VBS Blue Source"
set ortho "OrthoCam"
set tinToDem "TIN to DEM"
set mexRunner "Model Exchanger Runner 2"
set selArea "Select By Area"
set srfReproj "Reproject Image (B & W)"
set exporter_blend "Export VBS Blue Source DEM Blend Mask"
set ext_EVBS_nodes {}
set exporter1 "Export VBS Blue Source DEM"
set exporter2 "Export VBS Blue Source MOD"
set exporter3 "Export VBS Blue Source SRF"
set exporter4 "Export VBS Blue Source ALB"
lappend ext_EVBS_nodes $exporter1 $exporter2 $exporter3 $exporter4

#Configure Apply Feature and Model Library Script 2 to use variables from some file
tsdnsetoption $applylibraryscript automation true
tsdnsetoption $applylibraryscript cmdfile "sourceDir.txt" 
tsdnsetoption $apply_feature_and_library_script automation true
tsdnsetoption $apply_feature_and_library_script cmdfile "tileScheme.txt" 

#convert input offset to utm
puts "Convert input offset to utm"
set geocoordsys "Geodetic ang_units:Decimal_Degrees vert_units:Meters"
set geohdatum "WGS84"
set geovdatum "WGS84_ellipsoid"
set geooffset [tscconvertxyz $offset_coordsys $offset_hdatum $offset_vdatum $geocoordsys $geohdatum $geovdatum $offset_x $offset_y $offset_z]
set utmcoordsys [tscupdatezone {UTM zone:30 hemi:N horiz_units:Meters vert_units:Meters} [lindex $geooffset 1] [lindex $geooffset 0]]
set utmoffset [tscconvertxyz $offset_coordsys $offset_hdatum $offset_vdatum $utmcoordsys $geohdatum $geovdatum $offset_x $offset_y $offset_z]

puts "Input offset: $offset_x, $offset_y in coordinate system $offset_coordsys"
puts "Converted offset: [lindex $utmoffset 0],[lindex $utmoffset 1] in coordinate system $utmcoordsys" 
tsdsetvar "COORD_STRING" "$utmcoordsys"
tsdsetvar "VERT_DATUM" "$project_vdatum"

#Set offset values
puts "Setting data offset"
tsdnsetoption $offset dx [lindex $utmoffset 0]
tsdnsetoption $offset dy [lindex $utmoffset 1]
tsdnsetoption $offset dz [lindex $utmoffset 2]

#Set models offset values
if {[string length $offset_models] > 0} {
	tsdnsetoption $offset_2 dz $offset_models
}

#Set input of PDAL node to output of Export LAS
puts "Setting CSF options"
if {[llength $csf_options] > 0} {
	if {[llength $csf_options] != 6} {
		puts "CSF options string must have exactly 6 values"
		exit
	}
	tsdnsetoption $csf resolution [lindex $csf_options 0]
	tsdnsetoption $csf threshold [lindex $csf_options 1]
	tsdnsetoption $csf smooth [lindex $csf_options 2]
	tsdnsetoption $csf step [lindex $csf_options 3]
	tsdnsetoption $csf rigidness [lindex $csf_options 4]
	tsdnsetoption $csf iterations [lindex $csf_options 5]
}
tsdnsetoption $csf pdalPath "out22.las"

#Set input of Import LAS node to output of PDAL node
puts "Setting Import LAS options"
tsdnsetoption $import_las input "PDALTranslateOutput.las"

#Set clipped model prefixes to user defined name
puts "Setting Clip TSG options"
tsdnsetoption $clip_tsg prefix $name

#Set blender path for script runner node, as well as threads to run on
tsdnsetoption $blender blenderExe $blender_path
tsdnsetoption $blender multithread true
if {[string length $blender_threads] > 0} {
	tsdnsetoption $blender threads $blender_threads
}
tsdnsetoption $blender dir $out_in_name_with_drive
if {[string length $visualLODs] > 0} {
	tsdnsetoption $blender makeLODs $visualLODs
}
if {[string length $faceThresh] > 0} {
	tsdnsetoption $blender faceThresh $faceThresh
}
if {[string length $lodThresh] > 0} {
	tsdnsetoption $blender lodThresh $lodThresh
}


#Set export options
puts "Setting export options"
tsdnsetoption $exporter basename $name
tsdnsetoption $exporter dir $name
tsdnsetoption $exporter version $vbs4_version
tsdnsetoption $exporter overrideInstallation $override_Installation_VBS4_bool
tsdnsetoption $exporter overridePath $override_Path_VBS4
tsdnsetoption $exporter driveletter_radio $override_Installation_DevSuite
tsdnsetoption $exporter driveletter $override_Path_DevSuite

tsdnsetoption $exporter_blend basename $name
tsdnsetoption $exporter_blend dir $name
tsdnsetoption $exporter_blend version $vbs4_version
tsdnsetoption $exporter_blend overrideInstallation $override_Installation_VBS4_bool
tsdnsetoption $exporter_blend overridePath $override_Path_VBS4
tsdnsetoption $exporter_blend driveletter_radio $override_Installation_DevSuite
tsdnsetoption $exporter_blend driveletter $override_Path_DevSuite
tsdnsetoption $exporter_blend demAsMask true

#Set additional EVBS with exporter options, they don't run automatically 
foreach in_node $ext_EVBS_nodes {
	tsdnsetoption $in_node basename $name
	tsdnsetoption $in_node dir $name
	tsdnsetoption $in_node version $vbs4_version
	tsdnsetoption $in_node overrideInstallation $override_Installation_VBS4_bool
	tsdnsetoption $in_node overridePath $override_Path_VBS4
	tsdnsetoption $in_node driveletter_radio $override_Installation_DevSuite
	tsdnsetoption $in_node driveletter $override_Path_DevSuite
	}

#Set OrthoCam options
puts "Setting Raster Generation Options"
if {[string length $orthocam_Resolution] > 0} {
	tsdnsetoption $ortho resolution $orthocam_Resolution
}
if {[string length $orthocam_Render_Lowest] > 0} {
	tsdnsetoption $ortho renderLowest $orthocam_Render_Lowest
}
#Set resolution of created DEM
if {[string length $tin_to_dem_Resolution] > 0} {
	tsdnsetoption $tinToDem gsd $tin_to_dem_Resolution
}
#Set resolution of created SRF
if {[string length $srfResolution] > 0} {
	if {$srfResolution < 0.5} {
		puts "Warning: Surface mask resolution cannot be below 0.5m/px.  Setting to 0.5m/px"
		set srfResolution 0.5
	}
	tsdnsetoption $srfReproj output_res $srfResolution
}

puts "Setting mex VBS4 and devsuite options"
tsdnsetoption $mexRunner vbs4_radio $override_Installation_VBS4
tsdnsetoption $mexRunner vbs4 $override_Path_VBS4
tsdnsetoption $mexRunner version $vbs4_version
tsdnsetoption $mexRunner driveletter_radio $override_Installation_DevSuite
tsdnsetoption $mexRunner driveletter $override_Path_DevSuite
tsdnsetoption $mexRunner outname $out_in_name
tsdnsetoption $mexRunner dir $out_in_name_with_drive
if {[string length $collision] > 0} {
	tsdnsetoption $mexRunner geometryLOD $collision
}

puts "Setting Select by area size"
if {[string length $sel_Area_Size] > 0} {
	tsdnsetoption $selArea min_area $sel_Area_Size
}

set tsTimer [clock milliseconds]

#Update the Apply Model Library Script to import all models
puts -nonewline "Update Apply Model Library Script node"
flush stdout
tsdnupdate $applylibraryscript
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

#Update the Apply Model Library Script to import all models
puts -nonewline "Update Apply Feature and Model Library Script 2"
flush stdout
tsdnupdate $apply_feature_and_library_script
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

#Update the offset node so we will have a TBR to pull project bounds from for the rest of the processing
puts -nonewline "Updating Offset node"
flush stdout
tsdnupdate $offset
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

tav_open boundstav "n33.tbr"
set numpoints 0
boundstav pointapply p {
	incr numpoints 1
}
if {$numpoints eq 0} {
	puts "Error: No models imported.  Make sure your data folder points to the correct location."
	exit
}
boundstav free

#bounds setting in project after offset has ran
#Check Offset output to get bounds of file in seconds
set bounds [tsdcheckfilebounds "n33.tbr"]
puts "Setting corners"
set sw_corner [lindex $bounds 0]
set ne_corner [lindex $bounds 2]
set west [lindex $sw_corner 0]
set south [lindex $sw_corner 1]
set east [lindex $ne_corner 0]
set north [lindex $ne_corner 1]

#Convert bounds to Decimal Degrees
set fwest [expr {$west / 3600}]
set fsouth [expr {$south / 3600}]
set feast [expr {$east / 3600}]
set fnorth [expr {$north / 3600}]

#Convert Bounds to UTM
if {[string length $tileSize] > 0} {
	tsdsetvar "GRID" $tileSize
} else {
	set tileSize [tsdgetvar "GRID"]
}
	
puts "Setting CRS variables"
set icoord $geocoordsys
set ocoord $utmcoordsys
set hdatum $geohdatum
set vdatum $geovdatum
puts "Setting bounds variables"
set bnds [tsdconvertbounds $icoord $hdatum $vdatum $fwest $fsouth $feast $fnorth $ocoord $hdatum $vdatum]
set minx [expr {floor([lindex $bnds 0])}]
set miny [expr {floor([lindex $bnds 1])}]
set maxx [expr {ceil([lindex $bnds 2])}]
set maxy [expr {ceil([lindex $bnds 3])}]

set expand false
#expand bounds to next tile size
set minx [expr {floor($minx / $tileSize) * $tileSize}]
set miny [expr {floor($miny / $tileSize) * $tileSize}]
set maxx [expr {ceil($maxx / $tileSize) * $tileSize}]
set maxy [expr {ceil($maxy / $tileSize) * $tileSize}]

puts "Expanding project bounds to next tile size multiple"
puts "New project bounds:"
puts "West: $minx"
puts "East: $maxx"
puts "North: $miny"
puts "South: $maxy"

#Set bounds in Project Properties
puts "Setting project bounds to ($minx, $miny) - ($maxx, $maxy)"
tsdsetvar "MBR_XMIN" "$minx"
tsdsetvar "MBR_XMAX" "$maxx"
tsdsetvar "MBR_YMIN" "$miny"
tsdsetvar "MBR_YMAX" "$maxy"

#Update the Place Models node to place models
puts -nonewline "Update Place Models node"
flush stdout
tsdnupdate $place_models
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

#Update export LAS node
puts -nonewline "Updating Export LAS node"
flush stdout
tsdnupdate $export_las
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

#Update PDAL Translate CSF Node - Requires Export LAS node output
puts -nonewline "Updating CSF node"
flush stdout
tsdnupdate $csf
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

#Update Import LAS Node - Requires output of PDAL Translate CSF Node
puts -nonewline "Updating Import LAS node"
flush stdout
tsdnupdate $import_las
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

#Update TIN to DEM Node
puts -nonewline "Updating TIN to DEM node"
flush stdout
tsdnupdate $tinToDem
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

#Update Clip TSG by Polygons
puts -nonewline "Updating Clip TSG by Polygons node"
flush stdout
tsdnupdate $clip_tsg
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

#Update Blender Script Runner node
puts -nonewline "Updating Blender Script Runner node"
flush stdout
tsdnupdate $blender
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

#Update Model Exchanger Runner
puts -nonewline "Updating Model Exchanger Runner"
flush stdout
tsdnupdate $mexRunner
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

#Update orthoCam node
puts -nonewline "Updating OrthoCam"
flush stdout
tsdnupdate $ortho
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

#Update Export VBS Blue Source node
puts -nonewline "Updating Export VBS Blue Source Node"
flush stdout
tsdnupdate $exporter
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

#Update Export VBS Blue Source DEM Blend Mask node
puts -nonewline "Export VBS Blue Source DEM Blend Mask Node"
flush stdout
tsdnupdate $exporter_blend
tsdwait
tsdsave

set tsNewTimer [clock milliseconds]
set difference [expr ($tsNewTimer - $tsTimer)/1000]
puts " ... Completed in $difference seconds"
set tsTimer $tsNewTimer

#Get TT version
puts -nonewline "TerraTools version: [tsdgetversion]"
flush stdout 

exit
