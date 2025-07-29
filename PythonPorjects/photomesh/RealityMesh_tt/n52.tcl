tsa_open tsa [lindex $argv 1]
tav_open tav [lindex $argv 0]

tav pointapply p {
	if {![p has @mref_model]} {
		continue
	}

	set name [p get @mref_model]
	if {![tsa exists model $name]} {
		puts "$name doesnt exist"
		continue
	}
	
	tsa model $name m

	set box_min_x [m get "Box_Min x"]
	set box_max_x [m get "Box_Max x"]
	set box_min_y [m get "Box_Min y"]
	set box_max_y [m get "Box_Max y"]
	set box_min_z [m get "Box_Min z"]
	set box_max_z [m get "Box_Max z"]

	tav new_areal a
	a new_loop l
	a set -string @model $name
	set xmin [expr [lindex [p coordinates] 0] + $box_min_x]
	set xmax [expr [lindex [p coordinates] 0] + $box_max_x]
	set ymin [expr [lindex [p coordinates] 1] + $box_min_y]
	set ymax [expr [lindex [p coordinates] 1] + $box_max_y]
	l add_vertex $xmin $ymin 0
	l add_vertex $xmin $ymax 0
	l add_vertex $xmax $ymax 0
	l add_vertex $xmax $ymin 0
	l add_vertex $xmin $ymin 0
	p del -all *
}


tav save -remove_unattributed [lindex $argv 2]