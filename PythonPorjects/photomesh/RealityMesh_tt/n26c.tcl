tav_open tav [lindex $argv 0]
tsa_open tsa [lindex $argv 1]

set highest_lod_per_tile {}
set tilelist {}

#Defines
set max_tile_x 0
set max_tile_y 0
set numeric 0

if {[string equal $tileScheme "Numeric"]} { 
	set numeric 1
	puts "Using numeric mode"
}

puts "Using tile scheme: $tileScheme"

tsa modelapply m {
	if {$numeric} {break}
	set name [m get @name]
		
	scan [string tolower $name] "[string tolower $tileScheme]" tile_x tile_y lod
	
	#puts "$name : $tile_x $tile_y $lod"
	
	if {$tile_x > $max_tile_x} {
		set max_tile_x $tile_x
	}
	if {$tile_y > $max_tile_y} {
		set max_tile_y $tile_y
	}
	
	set entry {}
	lappend entry $tile_x
	lappend entry $tile_y
	lappend entry $lod
	
	lappend tilelist $entry
}

foreach tile $tilelist {
	set tile_x [lindex $tile 0]
	set tile_y [lindex $tile 1]
	set lod [lindex $tile 2]
	
	set tile_index [expr $tile_x * $max_tile_y + $tile_y]
	
	set result [lsearch -index 0 $highest_lod_per_tile $tile_index]
	
	if { $result == -1 } {
		set entry {}
		lappend entry $tile_index
		lappend entry $lod
		lappend highest_lod_per_tile $entry
	} else {
		set entry [lindex $highest_lod_per_tile $result]
		set max_lod [lindex $entry 1]
		
		if {$lod > $max_lod} {
			lset entry 1 $lod
			lset highest_lod_per_tile $result $entry
		}
	}
}

puts "highest_lod_per_tile = $highest_lod_per_tile"

tsa modelapply m {
	set name [m get @name]
	if {!$numeric} {
		scan $name "$tileScheme" tile_x tile_y lod
		
		#puts "$name : $tile_x $tile_y $lod"
		
		set tile_index [expr $tile_x * $max_tile_y + $tile_y]
		
		set result [lsearch -integer -exact -index 0 $highest_lod_per_tile $tile_index]
		set highest_lod [lindex [lindex $highest_lod_per_tile $result] 1]
	}
	if { $numeric || $lod == $highest_lod} {
	
		set tsgFile [m get File]
		
		puts "$name = $tsgFile"
		
		set box_min_x [m get "Box_Min x"]
		set box_max_x [m get "Box_Max x"]
		set box_min_y [m get "Box_Min y"]
		set box_max_y [m get "Box_Max y"]
		set box_min_z [m get "Box_Min z"]
		set box_max_z [m get "Box_Max z"]
		
		tsg_model_open tsg $tsgFile
    tsg insert_transform \
      1  0  0  [expr -1*$box_min_x] \
      0  0  1  [expr -1*$box_min_z] \
      0 -1  0  [expr -1*$box_min_y] \
      0  0  0  1
		set outputTSGFile "${tsgFile}_new2.ts0"
		tsg save $outputTSGFile
		
		m set File $outputTSGFile
	
		m set "Box_Min x" 0
		m set "Box_Max x" [expr $box_max_x - $box_min_x]
		m set "Box_Min y" 0
		m set "Box_Max y" [expr $box_max_z - $box_min_z]
		m set "Box_Min z" 0
		m set "Box_Max z" [expr $box_max_y - $box_min_y]
	
		tav new_point $box_min_x $box_min_z $box_min_y p
		p set @mref_model $name
		p set @mref_preview_mlib [lindex $argv 3]
		p set @mref_use_elev 1
		p set @vbsblue_instanced_object 1
	} else {
		m delete
	}
}

tav save [lindex $argv 2]
tsa save [lindex $argv 3]
