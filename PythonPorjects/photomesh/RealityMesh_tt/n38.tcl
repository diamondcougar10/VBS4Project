set modelDir OneClick_output
set mexExe P:/tools/ModelExchanger/ModelExchangerCmd.exe
set vbsBlueVersion blue.trunk
set tempDir vbs2/customer/structures/$modelDir

file mkdir P:/$tempDir
# Open input file.
brep_open world [lindex $argv 0]

set threads 50
set launched 0

world nodeapply n {
    if {[n hasattr @mref_model]} {
		incr launched 1
		if {$launched == $threads} {
			set launched 0
			after 30000
		}
		
		set modelName [n get @mref_model]
		set args "asset-converter --force --input \"P:/$modelDir/$modelName.glb\" --outputfilename \"$modelName\" --outputtype \"p3d\" --outputdirectory \"P:/$tempDir\" "
		puts "CMD> $mexExe $args"
		exec $mexExe {*}$args &
		puts ""
		n set @vbs2_model "[string map {/ \\} $tempDir]\\$modelName.p3d"
		n delattr @mref_model
	}
}

# Save to output file.
world save [lindex $argv 1]
