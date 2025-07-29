tsa_open tsa [lindex $argv 0]

tsa modelapply m {
	
	for {set i 0} {$i < [m numfeatures]} {incr i} {
		tsa feature [m getfeature $i] f
		f getappearance a
		a setmaterial "Default"		
	}
}

tsa save [lindex $argv 1]
